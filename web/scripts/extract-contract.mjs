#!/usr/bin/env node
/**
 * Экстрактор контракта из web/lib/types.ts (контракт: docs/web_contract_drift_execplan.md).
 *
 * Извлекает только типы, достижимые от корневых интерфейсов реестра
 * (tests/contracts/registry.json), в нормализованный JSON:
 *
 *   { "meta": {...sha256 источника и реестра...}, "roots": [...], "types": {
 *       "<Имя>": <ValueSpec>   // interface/alias; объектные — с fields
 *   } }
 *
 * ValueSpec: {kinds, literals, widened, items, fields, ref, wildcard}
 *   kinds ⊆ ["array","boolean","null","number","object","string"]
 *   literals — закрытое множество значений (advisory при widened=true)
 *   widened — union расширен голым `string` (проверка литералов не блокирует)
 *   items — спек элемента массива; fields — поля объекта; ref — ссылка на имя
 *   wildcard — Record<string, unknown>/unknown/any (принять что угодно)
 *
 * Поддерживается: interface (extends), alias, `?`, примитивы, null/undefined,
 * строковые/булевы/числовые литералы, union, `| string`, T[]/Array<T>,
 * инлайн-объекты, Record<string, unknown>, unknown/any, дженерики-инстанциации
 * (подстановка), Pick<A, "a"|"b">, пересечения A & B, индексированный доступ
 * A["key"].
 *
 * Fail-closed: неизвестная конструкция в достижимом графе — exit 1 с файлом:строкой.
 *
 * CLI: [--source <ts>] [--roots a,b,c] [--registry <json>] [--out <file>] [--check]
 * По умолчанию: source=web/lib/types.ts, roots=interface-имена из реестра.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(SCRIPT_DIR, "..");
const REPO_ROOT = path.resolve(WEB_DIR, "..");
const DEFAULT_SOURCE = path.join(WEB_DIR, "lib", "types.ts");
const DEFAULT_REGISTRY = path.join(REPO_ROOT, "tests", "contracts", "registry.json");

const KIND_ORDER = ["array", "boolean", "null", "number", "object", "string"];

function fail(message) {
  console.error(`extract-contract: ${message}`);
  process.exit(1);
}

function sha256(text) {
  return crypto.createHash("sha256").update(text, "utf-8").digest("hex");
}

function repoRelative(filePath) {
  const abs = path.resolve(filePath);
  const rel = path.relative(REPO_ROOT, abs);
  return rel.startsWith("..") ? abs.split(path.sep).join("/") : rel.split(path.sep).join("/");
}

function emptySpec() {
  return { kinds: [], literals: [], widened: false, items: null, fields: null, ref: null, wildcard: false, variants: null };
}

function normalizeSpec(spec) {
  const kinds = [...new Set(spec.kinds)].sort((a, b) => KIND_ORDER.indexOf(a) - KIND_ORDER.indexOf(b));
  const literals = [...new Set(spec.literals)].sort((a, b) => {
    const ta = typeof a;
    const tb = typeof b;
    if (ta !== tb) return ta < tb ? -1 : 1;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  return { ...spec, kinds, literals };
}

function sortedFields(fields) {
  const out = {};
  for (const key of Object.keys(fields).sort()) out[key] = fields[key];
  return out;
}

/** Разбор CLI. */
function parseArgs(argv) {
  const args = { source: null, roots: null, registry: DEFAULT_REGISTRY, out: null, check: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--source") args.source = argv[++i];
    else if (arg === "--roots") args.roots = argv[++i];
    else if (arg === "--registry") args.registry = argv[++i];
    else if (arg === "--out") args.out = argv[++i];
    else if (arg === "--check") args.check = true;
    else fail(`неизвестный аргумент: ${arg}`);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const sourcePath = args.source ? path.resolve(args.source) : DEFAULT_SOURCE;
const sourceText = fs.readFileSync(sourcePath, "utf-8");
const sourceFile = ts.createSourceFile(
  sourcePath,
  sourceText,
  ts.ScriptTarget.ES2022,
  /*setParentNodes*/ false,
  ts.ScriptKind.TS,
);

const decls = new Map();
for (const stmt of sourceFile.statements) {
  if (ts.isInterfaceDeclaration(stmt) || ts.isTypeAliasDeclaration(stmt)) decls.set(stmt.name.text, stmt);
}

function typeName(stmt) {
  return stmt.name.text;
}

function lineOf(node) {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
}

function unsupported(node, what) {
  fail(`${repoRelative(sourcePath)}:${lineOf(node)} unsupported ${what || ts.SyntaxKind[node.kind]} внутри достижимого графа`);
}

/** Тело объявленного типа (поля интерфейса / RHS алиаса) с подстановкой дженерик-аргументов. */
const bodyMemo = new Map();
const bodyInProgress = new Set();

function bodySpecOf(name, typeArgs, subst, site) {
  const decl = decls.get(name);
  if (!decl) fail(`${repoRelative(sourcePath)}:${lineOf(site)} unknown type reference ${name}`);
  const params = decl.typeParameters?.map(typeName) ?? [];
  if (params.length > 0) {
    if (!typeArgs || typeArgs.length !== params.length) {
      fail(
        `${repoRelative(sourcePath)}:${lineOf(site)} ${name} ожидает ${params.length} типовых аргументов`,
      );
    }
    const inner = { ...subst };
    params.forEach((param, index) => {
      inner[param] = typeArgs[index];
    });
    return buildBody(decl, inner);
  }
  if (bodyMemo.has(name)) return bodyMemo.get(name);
  if (bodyInProgress.has(name)) {
    fail(`${repoRelative(sourcePath)}:${lineOf(site)} циклическая инлайн-развёртка ${name}`);
  }
  bodyInProgress.add(name);
  const body = buildBody(decl, subst);
  bodyInProgress.delete(name);
  bodyMemo.set(name, body);
  reachable.add(name);
  return body;
}

function buildBody(decl, subst) {
  if (ts.isTypeAliasDeclaration(decl)) return specOf(decl.type, subst);
  const ctx = { fields: {}, wildcard: false };
  for (const heritage of decl.heritageClauses ?? []) {
    for (const expr of heritage.types) {
      if (!ts.isIdentifier(expr.expression)) unsupported(expr, "extends с не-идентификатором");
      const parent = bodySpecOf(expr.expression.text, expr.typeArguments ?? [], subst, expr);
      if (!parent.fields) unsupported(expr, `extends не-объектового типа ${expr.expression.text}`);
      Object.assign(ctx.fields, parent.fields);
      ctx.wildcard = ctx.wildcard || parent.wildcard;
    }
  }
  for (const member of decl.members) collectMember(member, ctx, subst);
  return { ...emptySpec(), kinds: ["object"], fields: sortedFields(ctx.fields), wildcard: ctx.wildcard };
}

function collectMember(member, ctx, subst) {
  if (ts.isPropertySignature(member)) {
    if (!member.type) unsupported(member, "поле без типа");
    let name;
    if (ts.isIdentifier(member.name)) name = member.name.text;
    else if (ts.isStringLiteral(member.name)) name = member.name.text;
    else unsupported(member, "имя поля");
    ctx.fields[name] = { optional: member.questionToken !== undefined, spec: specOf(member.type, subst) };
    return;
  }
  // [key: string]: unknown — объект открыт для необъявленных полей с любыми значениями.
  if (ts.isIndexSignatureDeclaration(member)) {
    const keyType = member.parameters[0]?.type;
    if (member.parameters.length === 1 && keyType && keyType.kind === ts.SyntaxKind.StringKeyword) {
      ctx.wildcard = true;
      return;
    }
  }
  unsupported(member, "член интерфейса");
}

function literalKeysOf(node, subst) {
  const spec = specOf(node, subst);
  if (spec.literals.length && spec.literals.every((value) => typeof value === "string")) return spec.literals;
  unsupported(node, "список ключей");
}

/** Спека значения в позиции типа. */
function specOf(node, subst) {
  if (ts.isParenthesizedTypeNode(node)) return specOf(node.type, subst);

  if (ts.isUnionTypeNode(node)) {
    const childSpecs = [];
    for (const part of node.types) {
      if (part.kind === ts.SyntaxKind.UndefinedKeyword) continue; // опциональность — не значение
      childSpecs.push(specOf(part, subst));
    }
    // Дискриминированные union'ы объектов: {kind:"event",...} | {kind:"rolling",...}
    const objectChildren = childSpecs.filter(
      (child) => child.fields || (child.ref && child.kinds.includes("object")),
    );
    const useVariants = objectChildren.length > 1;

    const merged = emptySpec();
    const refs = new Set();
    let hasBareString = false;
    for (const child of childSpecs) {
      if (child.ref) refs.add(child.ref);
      merged.kinds.push(...child.kinds);
      merged.literals.push(...child.literals);
      merged.widened = merged.widened || child.widened;
      merged.wildcard = merged.wildcard || child.wildcard;
      if (
        child.kinds.length === 1 &&
        child.kinds[0] === "string" &&
        child.literals.length === 0 &&
        !child.ref &&
        !child.items &&
        !child.fields
      ) {
        hasBareString = true;
      }
      if (child.items) {
        if (merged.items) unsupported(node, "union разных массивов");
        merged.items = child.items;
      }
      if (!useVariants && child.fields) {
        for (const [key, field] of Object.entries(child.fields)) {
          if (fieldsOverlapConflict(merged.fields, key, field)) unsupported(node, "union конфликтующих объектов");
          merged.fields = { ...(merged.fields ?? {}), [key]: field };
        }
      }
    }
    if (useVariants) {
      merged.variants = objectChildren;
      merged.fields = null;
      merged.ref = null;
    } else {
      if (refs.size > 1) unsupported(node, "union разных ссылок");
      merged.ref = refs.size === 1 ? [...refs][0] : null;
    }
    // Голый `string` рядом с литералами превращает множество литералов в advisory.
    if (hasBareString && merged.literals.length > 0) merged.widened = true;
    return normalizeSpec(merged);
  }

  if (ts.isLiteralTypeNode(node)) {
    if (ts.isStringLiteral(node.literal)) {
      return { ...emptySpec(), kinds: ["string"], literals: [node.literal.text] };
    }
    if (node.literal.kind === ts.SyntaxKind.TrueKeyword || node.literal.kind === ts.SyntaxKind.FalseKeyword) {
      return { ...emptySpec(), kinds: ["boolean"], literals: [node.literal.kind === ts.SyntaxKind.TrueKeyword] };
    }
    if (ts.isNumericLiteral(node.literal)) {
      return { ...emptySpec(), kinds: ["number"], literals: [Number(node.literal.text)] };
    }
    if (node.literal.kind === ts.SyntaxKind.NullKeyword) {
      return { ...emptySpec(), kinds: ["null"] };
    }
    if (node.literal.kind === ts.SyntaxKind.UndefinedKeyword) {
      return emptySpec();
    }
    unsupported(node, "литерал");
  }

  if (
    node.kind === ts.SyntaxKind.StringKeyword ||
    node.kind === ts.SyntaxKind.NumberKeyword ||
    node.kind === ts.SyntaxKind.BooleanKeyword ||
    node.kind === ts.SyntaxKind.NullKeyword ||
    node.kind === ts.SyntaxKind.UndefinedKeyword ||
    node.kind === ts.SyntaxKind.AnyKeyword ||
    node.kind === ts.SyntaxKind.UnknownKeyword
  ) {
    if (node.kind === ts.SyntaxKind.AnyKeyword || node.kind === ts.SyntaxKind.UnknownKeyword) {
      return { ...emptySpec(), wildcard: true };
    }
    if (node.kind === ts.SyntaxKind.UndefinedKeyword) {
      return emptySpec();
    }
    const kindByKeyword = {
      [ts.SyntaxKind.StringKeyword]: "string",
      [ts.SyntaxKind.NumberKeyword]: "number",
      [ts.SyntaxKind.BooleanKeyword]: "boolean",
      [ts.SyntaxKind.NullKeyword]: "null",
    };
    return { ...emptySpec(), kinds: [kindByKeyword[node.kind]] };
  }

  if (ts.isArrayTypeNode(node)) {
    return { ...emptySpec(), kinds: ["array"], items: specOf(node.elementType, subst) };
  }

  if (ts.isTupleTypeNode(node)) {
    // `[]` в union — семантика «пустой массив»; непустые кортежи не поддерживаем.
    if (node.elements.length === 0) {
      return { ...emptySpec(), kinds: ["array"], items: { ...emptySpec(), wildcard: true } };
    }
    unsupported(node, "TupleType");
  }

  if (ts.isTypeLiteralNode(node)) {
    const ctx = { fields: {}, wildcard: false };
    for (const member of node.members) collectMember(member, ctx, subst);
    return { ...emptySpec(), kinds: ["object"], fields: sortedFields(ctx.fields), wildcard: ctx.wildcard };
  }

  if (ts.isTypeReferenceNode(node)) {
    if (!ts.isIdentifier(node.typeName)) unsupported(node, "qualified type reference");
    const name = node.typeName.text;
    const typeArgs = node.typeArguments ?? [];
    if (subst && subst[name]) return specOf(subst[name], subst);
    if (name === "Array" && typeArgs.length === 1) {
      return { ...emptySpec(), kinds: ["array"], items: specOf(typeArgs[0], subst) };
    }
    if (name === "Record" && typeArgs.length === 2) {
      return { ...emptySpec(), kinds: ["object"], wildcard: true };
    }
    if (name === "Pick" && typeArgs.length === 2) {
      const objectSpec = resolveObjectSpec(typeArgs[0], subst);
      const picked = {};
      for (const key of literalKeysOf(typeArgs[1], subst)) {
        const field = objectSpec.fields?.[key];
        if (!field) unsupported(node, `Pick: нет поля ${key}`);
        picked[key] = field;
      }
      return { ...emptySpec(), kinds: ["object"], fields: sortedFields(picked) };
    }
    if (decls.has(name)) {
      const decl = decls.get(name);
      if (decl.typeParameters?.length) {
        return bodySpecOf(name, typeArgs, subst, node); // дженерик развёрнут инлайн
      }
      if (ts.isInterfaceDeclaration(decl)) {
        // Тело строится отложенно (очередь pending): самоссылки интерфейсов легальны.
        pending.add(name);
        return { ...emptySpec(), kinds: ["object"], ref: name };
      }
      const body = bodySpecOf(name, [], subst, node);
      return { ...emptySpec(), kinds: body.kinds, literals: body.literals, widened: body.widened, ref: name };
    }
    unsupported(node, `unknown type reference ${name}`);
  }

  if (ts.isIntersectionTypeNode(node)) {
    const fields = {};
    for (const part of node.types) {
      const child = resolveObjectSpec(part, subst);
      for (const [key, field] of Object.entries(child.fields ?? {})) {
        if (fieldsOverlapConflict(fields, key, field)) unsupported(node, "пересечение конфликтующих полей");
        fields[key] = field;
      }
    }
    return { ...emptySpec(), kinds: ["object"], fields: sortedFields(fields) };
  }

  if (ts.isIndexedAccessTypeNode(node)) {
    const objectSpec = resolveObjectSpec(node.objectType, subst);
    if (!ts.isLiteralTypeNode(node.indexType) || !ts.isStringLiteral(node.indexType.literal)) {
      unsupported(node, "индексированный доступ с не-строковым литералом");
    }
    const field = objectSpec.fields?.[node.indexType.literal.text];
    if (!field) unsupported(node, `индексированный доступ: нет поля ${node.indexType.literal.text}`);
    return field.spec;
  }

  unsupported(node);
}

function fieldsOverlapConflict(fields, key, field) {
  return Boolean(fields && fields[key] && JSON.stringify(fields[key]) !== JSON.stringify(field));
}

/** Спека объекта с полями: инлайн, ref (разрешается по объявлениям) или пересечение. */
function resolveObjectSpec(node, subst) {
  const spec = specOf(node, subst);
  if (spec.fields) return spec;
  if (spec.ref) {
    const body = bodySpecOf(spec.ref, [], subst, node);
    if (!body.fields) unsupported(node, `не-объектовая ссылка ${spec.ref}`);
    return body;
  }
  if (spec.wildcard) return { ...emptySpec(), kinds: ["object"], wildcard: true };
  unsupported(node, "ожидался объектный тип");
}

// --- Корни и сборка артефакта ------------------------------------------------

const reachable = new Set();
const pending = new Set();

let roots;
let meta;
if (args.roots) {
  roots = args.roots.split(",").map((name) => name.trim()).filter(Boolean);
  meta = { source: repoRelative(sourcePath), source_sha256: sha256(sourceText) };
} else {
  const registryPath = path.resolve(args.registry);
  const registry = JSON.parse(fs.readFileSync(registryPath, "utf-8"));
  roots = [...new Set(Object.values(registry.endpoints).map((entry) => entry.interface))].sort();
  meta = {
    source: repoRelative(sourcePath),
    source_sha256: sha256(sourceText),
    registry: repoRelative(registryPath),
    registry_sha256: sha256(fs.readFileSync(registryPath, "utf-8")),
  };
}

for (const root of roots) {
  if (!decls.has(root)) fail(`корень реестра не найден в ${repoRelative(sourcePath)}: ${root}`);
  bodySpecOf(root, [], {}, sourceFile);
}
while (pending.size > 0) {
  for (const name of [...pending]) {
    pending.delete(name);
    if (!bodyMemo.has(name)) bodySpecOf(name, [], {}, sourceFile);
  }
}

const types = {};
for (const name of [...reachable].sort()) {
  const body = bodyMemo.get(name);
  if (body) types[name] = body;
}

const payload = { meta, roots: [...roots].sort(), types };
const output = `${JSON.stringify(payload, null, 2)}\n`;

if (args.check) {
  if (!args.out) fail("--check требует --out");
  const target = path.resolve(args.out);
  if (!fs.existsSync(target)) fail(`артефакт не найден: ${target}; выполните генерацию без --check`);
  const current = fs.readFileSync(target, "utf-8");
  if (current !== output) {
    const currentLines = current.split("\n");
    const outputLines = output.split("\n");
    let diffLine = 0;
    while (diffLine < Math.max(currentLines.length, outputLines.length) && currentLines[diffLine] === outputLines[diffLine]) {
      diffLine += 1;
    }
    fail(
      `артефакт устарел: ${repoRelative(target)}; первое расхождение в строке ${diffLine + 1}.\n` +
        "Выполните: npm --prefix web run contract:extract",
    );
  }
  process.stderr.write(`extract-contract: артефакт актуален (${repoRelative(target)})\n`);
  process.exit(0);
}

if (args.out) {
  fs.writeFileSync(path.resolve(args.out), output, "utf-8");
  process.stderr.write(`extract-contract: записан ${repoRelative(path.resolve(args.out))}\n`);
  process.exit(0);
}
process.stdout.write(output);
