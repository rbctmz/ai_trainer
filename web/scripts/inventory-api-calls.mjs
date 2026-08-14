#!/usr/bin/env node
/**
 * Инвентаризация API-вызовов фронтенда (контракт: docs/web_contract_drift_execplan.md).
 *
 * Обходит AST web/app/** и web/components/** через TypeScript Compiler API,
 * находит вызовы useSWR/fetcher/postJSON/putJSON/deleteJSON с путями /api/*
 * и печатает детерминированный JSON-инвентарь на stdout.
 *
 * Разрешаются автоматически: строковые литералы; шаблонные строки с интерполяцией
 * вида ${id}, ${obj.prop}, ${encodeURIComponent(x)}; тернарники с null-веткой и
 * простыми ветками; локальные const-ключи с разрешаемым инициализатором.
 *
 * Аннотации в комментариях над оператором вызова:
 *   // api-contract: exclude: <причина>   — вызов вне сети инвентаризации
 *   // api-contract: manual: /api/путь    — путь известен вручную (динамическая сборка)
 *
 * Fail-closed: неизвестная конструкция в позиции пути делает вызов «неразрешимым»
 * (unresolved) — Python-тест потребует аннотацию или запись в excluded реестра.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIR = path.resolve(SCRIPT_DIR, "..");
const SCAN_ROOTS = [path.join(WEB_DIR, "app"), path.join(WEB_DIR, "components")];
const CALL_METHOD = {
  useSWR: "GET",
  fetcher: "GET",
  postJSON: "POST",
  putJSON: "PUT",
  deleteJSON: "DELETE",
};
const MAX_COMBINATIONS = 16;
const MAX_DEPTH = 6;

function fail(message) {
  console.error(`inventory-api-calls: ${message}`);
  process.exit(1);
}

function listSourceFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listSourceFiles(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

/** Кандидаты-шаблоны полного пути; null = неразрешимо. Элемент "*"/"{x}" — плейсхолдеры. */
/** Текст простой цепочки полей: obj, obj.prop, obj.prop.sub — иначе null. */
function dottedText(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isPropertyAccessExpression(node)) {
    const base = dottedText(node.expression);
    return base === null ? null : `${base}.${node.name.text}`;
  }
  return null;
}

/**
 * Кандидаты-шаблоны полного пути; null = неразрешимо.
 * inInterpolation: узел стоит внутри ${...} — идентификаторы дают плейсхолдер {name},
 * а в корневой позиции идентификатор обязан разрешаться через const-карту.
 */
function patternsOf(node, constMap, usedConsts, depth, inInterpolation = false) {
  if (!node || depth > MAX_DEPTH) return null;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return [node.text];
  if (ts.isTemplateExpression(node)) {
    const combinations = [node.head.text];
    for (const span of node.templateSpans) {
      const inner = patternsOf(span.expression, constMap, usedConsts, depth + 1, true);
      if (inner === null) return null;
      const next = [];
      for (const prefix of combinations) {
        for (const variant of inner) next.push(prefix + variant + span.literal.text);
        if (next.length > MAX_COMBINATIONS) return null;
      }
      combinations.length = 0;
      combinations.push(...next);
    }
    return combinations;
  }
  if (ts.isIdentifier(node)) {
    if (inInterpolation) return [`{${node.text}}`];
    const bound = constMap.get(node.text);
    if (!bound) return null;
    usedConsts.add(bound.declaration);
    return patternsOf(bound.initializer, constMap, usedConsts, depth + 1, false);
  }
  if (ts.isPropertyAccessExpression(node)) {
    const dotted = dottedText(node);
    return dotted === null ? null : [`{${dotted.split(".").pop()}}`];
  }
  if (
    ts.isCallExpression(node) &&
    ts.isIdentifier(node.expression) &&
    node.expression.text === "encodeURIComponent" &&
    node.arguments.length === 1
  ) {
    return patternsOf(node.arguments[0], constMap, usedConsts, depth + 1, true);
  }
  // Нуль-арный вызов метода простого приёмника: searchQuery.trim()
  if (
    ts.isCallExpression(node) &&
    node.arguments.length === 0 &&
    ts.isPropertyAccessExpression(node.expression)
  ) {
    const receiver = dottedText(node.expression.expression);
    if (receiver !== null) return [`{${receiver.split(".").pop()}}`];
    return null;
  }
  if (ts.isConditionalExpression(node)) {
    const whenTrue = isNullish(node.whenTrue) ? [] : patternsOf(node.whenTrue, constMap, usedConsts, depth + 1, inInterpolation);
    const whenFalse = isNullish(node.whenFalse) ? [] : patternsOf(node.whenFalse, constMap, usedConsts, depth + 1, inInterpolation);
    if (whenTrue === null || whenFalse === null) return null;
    return [...whenTrue, ...whenFalse];
  }
  return null;
}

function isNullish(node) {
  if (!node) return false;
  if (node.kind === ts.SyntaxKind.NullKeyword || node.kind === ts.SyntaxKind.UndefinedKeyword) return true;
  return ts.isIdentifier(node) && node.text === "undefined";
}

const PLACEHOLDER = /^\{[a-zA-Z0-9_.]+\}$/;
const PLAIN_VALUE = /^[A-Za-z0-9._\-,%]+$/;

/** "/api/x?a={q}&b=1" -> {path, query}. Не-/api шаблоны отбрасываются. */
function splitPath(template) {
  if (!template.startsWith("/api")) return null;
  const [rawPath, rawQuery] = template.split("?", 2);
  const query = {};
  if (rawQuery) {
    for (const pair of rawQuery.split("&")) {
      if (!pair) continue;
      const eq = pair.indexOf("=");
      if (eq === -1) continue;
      const key = pair.slice(0, eq);
      const value = pair.slice(eq + 1);
      if (!PLACEHOLDER.test(value) && !PLAIN_VALUE.test(value)) continue;
      query[key] = value;
    }
  }
  return { path: rawPath, query };
}

function statementOf(node) {
  let cur = node;
  while (cur.parent && !ts.isStatement(cur)) cur = cur.parent;
  return cur;
}

function annotationOf(statement, src) {
  const ranges = ts.getLeadingCommentRanges(src, statement.getFullStart()) || [];
  for (const range of ranges) {
    const text = src.slice(range.pos, range.end);
    if (text.includes("api-contract: exclude")) return { excluded: true };
    const manual = text.match(/api-contract:\s*manual:\s*(\/api\/[A-Za-z0-9_\-/.{}]*)/);
    if (manual) return { excluded: false, manualPath: manual[1] };
  }
  return null;
}

function libTypesImports(sourceFile) {
  const names = new Set();
  for (const stmt of sourceFile.statements) {
    if (!ts.isImportDeclaration(stmt) || !ts.isStringLiteral(stmt.moduleSpecifier)) continue;
    if (stmt.moduleSpecifier.text !== "@/lib/types") continue;
    const bindings = stmt.importClause?.namedBindings;
    if (stmt.importClause?.name) names.add(stmt.importClause.name.text);
    if (bindings && ts.isNamedImports(bindings)) {
      for (const el of bindings.elements) names.add(el.name.text);
    }
  }
  return names;
}

function typeArgumentOf(call, sourceFile, libNames) {
  const typeNode = call.typeArguments?.[0];
  if (!typeNode) return { type: null, type_source: "none" };
  const text = sourceFile.text.slice(typeNode.getStart(sourceFile), typeNode.getEnd());
  const typeName = ts.isTypeReferenceNode(typeNode) && ts.isIdentifier(typeNode.typeName) ? typeNode.typeName.text : null;
  if (typeName && libNames.has(typeName)) return { type: text, type_source: "lib/types" };
  if (typeName) return { type: text, type_source: "local" };
  return { type: text, type_source: "inline" };
}

function scanFile(absPath, relPath) {
  const src = fs.readFileSync(absPath, "utf-8");
  const sourceFile = ts.createSourceFile(absPath, src, ts.ScriptTarget.ES2022, /*setParentNodes*/ true, absPath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);

  const constMap = new Map();
  const collectConsts = (node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      constMap.set(node.name.text, { declaration: node, initializer: node.initializer });
    }
    ts.forEachChild(node, collectConsts);
  };
  collectConsts(sourceFile);

  const libNames = libTypesImports(sourceFile);
  const calls = [];

  const visit = (node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text in CALL_METHOD) {
      const kind = node.expression.text;
      const arg = node.arguments[0];
      if (arg) {
        if (isNullish(arg)) {
          ts.forEachChild(node, visit);
          return;
        }
        const statement = statementOf(node);
        const annotation = annotationOf(statement, src);
        const entry = {
          file: relPath,
          line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
          kind,
          method: CALL_METHOD[kind],
        };
        if (annotation?.excluded) {
          calls.push({ ...entry, paths: [], type: null, type_source: "none", unresolved: null, annotated: true });
        } else {
          const usedConsts = new Set();
          const patterns = patternsOf(arg, constMap, usedConsts, 0);
          const resolveSource = annotation?.manualPath ? [annotation.manualPath] : patterns;
          if (resolveSource === null) {
            calls.push({
              ...entry,
              paths: [],
              ...typeArgumentOf(node, sourceFile, libNames),
              unresolved: src.slice(arg.getStart(sourceFile), arg.getEnd()),
              annotated: Boolean(annotation),
            });
          } else {
            const seen = new Set();
            const paths = [];
            for (const template of resolveSource) {
              const split = splitPath(template);
              if (!split) continue;
              const key = JSON.stringify([split.path, split.query]);
              if (seen.has(key)) continue;
              seen.add(key);
              paths.push(split);
            }
            calls.push({
              ...entry,
              paths,
              ...typeArgumentOf(node, sourceFile, libNames),
              unresolved: paths.length ? null : src.slice(arg.getStart(sourceFile), arg.getEnd()),
              annotated: Boolean(annotation),
            });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return calls;
}

try {
  const files = SCAN_ROOTS.flatMap(listSourceFiles);
  const calls = files
    .flatMap((absPath) =>
      scanFile(absPath, path.join("web", path.relative(WEB_DIR, absPath)).split(path.sep).join("/")),
    )
    .sort((a, b) => (a.file === b.file ? a.line - b.line : a.file.localeCompare(b.file)));
  process.stdout.write(`${JSON.stringify({ files_scanned: files.length, calls }, null, 2)}\n`);
} catch (error) {
  fail(error && error.stack ? error.stack : String(error));
}
