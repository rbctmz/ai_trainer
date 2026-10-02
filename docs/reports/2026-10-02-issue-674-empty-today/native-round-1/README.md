# PR #676: исправления native review round 1

Reviewed head: `1a85c235892a1750127f08aa10c25a2894485bf1`.
Оба замечания **fixed-in `7e75e470c08a536e436dac98b8f6694554565735`**.
Luna — Domain/API Implementer; Sol — независимый Reviewer, затем Integrator.
Scope: два замечания к guard пустого дня и точные saved-checkpoint регрессии.

## N1: целые числа вне диапазона float

[Native P2](https://github.com/rbctmz/ai_trainer/pull/676#discussion_r4164541704).
**Observed:** сохранённые `duration_minutes=10**400` и `total_tss=10**400`
переживают JSON save/restore и вызывают OverflowError в новой проверке.
**Inferred:** причина — преобразование Python int в float внутри `math.isfinite`;
дешёвая опровергающая проверка — сравнение того же int непосредственно с нулём.
**Verified by:** отдельный probe на reviewed head и RED тесты обеих веток.
Исправление сравнивает int с нулём без преобразования; bool исключён, конечность
float по-прежнему проверяется. Карточка сохраняется вместо нового подтверждения отдыха.

## N2: противоречащие исполнимые данные

[Native P2](https://github.com/rbctmz/ai_trainer/pull/676#discussion_r4164541714).
**Observed:** nonempty `materialized_steps` и `legs` сохраняются в checkpoint,
но guard на reviewed head возвращает пустой день и Today.session=null.
**Inferred:** после sessions=[] guard не проверял остальные исполнимые поля;
дешёвая опровергающая проверка — сохранить тот же checkpoint с этими полями.
**Verified by:** независимый RED probe и тесты обеих веток.
Теперь при наличии эти поля должны быть пустыми списками. Nonempty и malformed
значения сохраняют прежнюю проекцию; отсутствие полей допустимо.

## Доказательства

- Luna RED: [8 failed](luna-red.txt), дополнительно [4 malformed failed](luna-malformed-red.txt).
- Независимый probe на reviewed head: [4 failed](independent-red.txt).
- Today на исправленных исходниках: [42 passed](today-green.txt).
- Независимый focused Today/Planning/session projection/checkpoint history + probe:
  [101 passed](independent-green.txt), из них 97 tracked и 4 внешних probe.
- Contributor-safe: [2990 passed, 18 skipped, 46 deselected](contributor-safe.txt).
- [8 контрольных API-сценариев](api-green.txt) после настоящего save/restore: passed.
- Ruff всего репозитория (`--no-cache`), git diff --check: passed.
- [SHA-256 проверенных product/test файлов](source-hashes.json).

12 tracked регрессий выполняются в `tests/smoke/test_api_today.py`.
[Независимый probe](independent-probe.txt) использует те же синтетические builders,
но самостоятельно сохраняет и восстанавливает checkpoint и вызывает Today adapter.
Первый объединённый запуск этого probe остановился в science audit при создании
плана с заведомо некорректной длительностью, до проверяемого Today guard. Fixture
исправлена: сначала строится корректный checkpoint, затем повреждаются сохраняемые
метаданные. На reviewed head исправленная fixture воспроизводит все четыре дефекта;
на исправлении и в объединённом focused run она зелёная. Science audit не менялся.

Все Python проверки изолированы от .env, сети и личной SQLite. Source export для
полного набора проверен по bytes; runtime каталоги удалены автоматически.
UI/DTO не менялись: web lint/build/contracts и 48 браузерных состояний в родительском
отчёте относятся к предыдущему head. Текущие API controls повторены. Новое локальное
ревью ограничено delta после `1a85c23`; native round 1 этим не заменяется.
Remote CI, новый scoped native result, owner acceptance и мёрж — отдельные состояния.
