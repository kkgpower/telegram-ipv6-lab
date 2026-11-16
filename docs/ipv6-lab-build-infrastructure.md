# Инфраструктура сборки IPv6 Lab APK

Проверено 2026-11-16. База — `e3bde6d2a7a2835ac2a36754c662dbc89715b160`,
ветка инфраструктуры — `ci/ipv6-lab-apk-infrastructure`. Эта работа не требует
слияния с `master` или изменения исходного IPv6-исправления, DNS и обычной
конфигурации Telegram. Собственные Telegram API ID/API hash пока отсутствуют.
**APK не выпущен.** No-secrets CI успешно собрал полные нативные цели Telegram
для Android ARM64 и разрешил Gradle dependency metadata. Java-компиляция приложения,
упаковка и подписывание APK остаются непроверенными до получения собственных API.

Workflow опубликован в этой отдельной ветке и уже запущен без Secrets. Первый
[прогон](https://github.com/kkgpower/telegram-ipv6-lab/actions/runs/43832210881)
подтвердил работу runner, установку точных SDK packages и быстрые тесты; слишком
строгая проверка optional submodule остановила дальнейшие проверки. Исправление
проверки готовности прошло во
[втором прогоне](https://github.com/kkgpower/telegram-ipv6-lab/actions/runs/43833803895).
Затем [третий прогон](https://github.com/kkgpower/telegram-ipv6-lab/actions/runs/43835203652)
успешно собрал также `tmessages.49` и `twidget`. Ни одного build-tag и ни одной
подписанной сборки при этой проверке не создавалось.

## Фактические результаты

Проверенный код инфраструктуры — `b1b2ec3ba19cbaf04428bc501882a18dfe055d20`.
Последующий коммит отчёта меняет только документацию и сохранённые результаты.
Успешный третий validation job занял около 21 минуты; подписанный job пропущен.

| Проверка в третьем прогоне | Результат |
| --- | --- |
| Unit guards CI и submodule policy | 22/22 PASS |
| Реальный TCP/epoll host harness | 12/12 PASS |
| Offline Gradle profile probes | 5/5 PASS |
| SDK 36, Build Tools 36.0.0, NDK 27.2, CMake 3.22.1 | Нужные версии установлены |
| Обязательные recursive submodules | 22 на pinned SHA; optional test262 пропущен по upstream policy |
| Arm64 native archives | Все 16 файлов присутствуют, заголовки ar проверены |
| ConnectionSocket → Android AArch64 ELF | PASS, 0,57 с |
| Полная CMake-конфигурация | PASS, 0,62 с |
| `tgnet` | PASS, 16,86 с |
| `tmessages.49` и `twidget`, compile/link | PASS, 1009,47 с (16 мин 49 с) |
| Gradle debugCompileClasspath metadata | PASS, 100,60 с |
| APK, подпись, установка, MTProto на телефоне | Не выполнялись |

Для полной нативной команды `/usr/bin/time -v` сообщил child peak RSS
2 455 860 КиБ (около 2,34 ГиБ). Это максимум дочернего процесса, а не суммарная
память всей VM или одновременно работающих JVM/native процессов будущей сборки.
Проверка metadata не покрывает все artifact transforms, Java/Dex и APK packaging.

Сохранены [итог job и digest ZIP](ipv6-lab-ci-results/github-run-3/run-summary.json),
[native/dependency проверки](ipv6-lab-ci-results/github-run-3/verification-report.json),
[версии и исходники](ipv6-lab-ci-results/github-run-3/toolchain-report.json),
[ресурсы](ipv6-lab-ci-results/github-run-3/resource-report.json), host/profile logs.
Архив validation скачан и проверен по SHA-256, указанному GitHub; в Git сохранены
только шесть разрешённых отчётов и публичная сводка. Срок Actions artifacts — 3 дня,
поэтому копии отчётов в репозитории сохраняют результат после удаления artifact.

## Выбор среды

| Среда | CPU | RAM | Диск | Время одного job |
| --- | --- | --- | --- | --- |
| Этот Codex Cloud, измерено | 2 CPU по cgroup | 8 ГиБ по cgroup | overlay 7,9 ГиБ; около 6,3 ГиБ свободно до следующих загрузок | Лимит полной задачи не установлен измерением |
| GitHub Actions `ubuntu-24.04`, public repo | 4 | 16 GB | опубликованная спецификация SSD 14 GB | До 6 часов |
| Тот же label, private repo | 2 | 8 GB | опубликованная спецификация SSD 14 GB | До 6 часов |
| Larger Ubuntu, один из вариантов | 4 | 16 GB | SSD 150 GB | До 6 часов |

Спецификации GitHub — [standard runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job),
[larger runners](https://docs.github.com/en/actions/reference/runners/larger-runners),
[ограничения времени](https://docs.github.com/en/actions/reference/limits).
Опубликованные 14 GB нельзя объявлять гарантированно свободным местом конкретной
VM: `df -h`, фактический образ и расход после checkout/install фиксируются в job.
Проверка локального Codex также относится к этой машине, а не ко всем возможным
конфигурациям продукта.

В фактическом первом hosted-прогоне получен image `20261111.370.1`: 4 CPU,
16 760 344 576 байт RAM (около 15,6 ГиБ), файловая система 154 894 188 544 байта
(около 144,3 ГиБ). После SDK и submodules было свободно 86 592 647 168 байт
(около 80,6 ГиБ). Это наблюдение конкретной VM, а не обещание аналогичного диска
каждому запуску. Источник —
[сохранённый resource-report.json](ipv6-lab-ci-results/github-run-1/resource-report.json).
После установки SDK в Codex свободно около 4 ГиБ; после дополнительных заголовков
и arm64 archives — около 3,7 ГиБ. Диск и RAM этой локальной среды намного теснее.

Для public-репозитория стандартный Actions runner даёт больше CPU/RAM, чем
текущий Codex, и рекомендуется для полной arm64 сборки. Третий прогон подтвердил
достаточность для полного native compile/link: 4 CPU, около 15,3 ГиБ RAM и
84 ГиБ свободного места после подготовки, image `20261111.127.1`. Полный APK
пока не проверен. Текущее облачное окружение подходит для анализа, host-тестов и подготовки
инструментов; его небольшой общий диск ограничивает холодную Android-сборку.

Larger runners доступны организациям/enterprise на GitHub Team или Enterprise
Cloud и требуют настроенного доступа и биллинга. Для личного репозитория
`kkgpower` их наличие не предполагается. При OOM/ENOSPC понадобится доступный
более вместительный runner или контролируемая отдельная self-hosted машина.
Это запасной вариант, а не включённая платная услуга.
[Доступность и оплата larger runners](https://docs.github.com/en/actions/concepts/runners/larger-runners).

## Что занимает место и память

Для зафиксированных файлов получены ориентиры: около 423 МиБ source-файлов,
около 55,55 МиБ arm64 prebuilt archives; полный NDK r27c содержит около 1,91 ГиБ
распакованных данных. Эти числа не являются оценкой пика всей сборки. Git objects,
checkout и вложенные submodule, Maven/Gradle caches, Java/Dex outputs и native
intermediates учитываются дополнительно. Размер архива NDK при загрузке тоже
потребует временного места.

В текущем исследовательском checkout отсутствовали 21 зафиксированный submodule
и 16 arm64 `.a`. Получение SDK не заменяет эти файлы. Полное дерево и состояние
зависимостей должны проверяться до ввода подписывающих secrets.

Аудит Git metadata подтвердил доступность всех 21 top-level pinned commits,
вложенного QuickJS и его optional `test262`. Минимум superproject + 20 GitHub
submodules + распакованный NDK — около 3,27 ГиБ, ещё без libyuv, Git storage,
остальных SDK, Gradle caches и build intermediates.

QuickJS в upstream задаёт `test262` как `update = none`: это JavaScript test suite,
не входящий в Android APK. После recursive checkout видны 23 записи: 22 нужных
модуля на закреплённых SHA и один намеренно пропущенный. Helper читает политику
из **committed** `.gitmodules` владельца, а не из локального `.git/config`.
Отсутствие обязательного модуля или другой SHA по-прежнему блокируют сборку.

В CMake включены debug information и full LTO; native link может потребовать
существенной памяти. Один Gradle worker и arm64-only уменьшают нагрузку, но не
доказывают, что все этапы поместятся в 8 ГиБ. Время и child peak RSS полной
нативной команды измерены выше; пик всей APK-сборки пока не измерен.
Не следует представлять предполагаемые размеры intermediates как
проверенный факт или обещать завершение в лимит hosted job.
Флаги full LTO заданы корневым CMake; `jni/voip/CMakeLists.txt` переопределяет
C++ flags, поэтому нельзя распространять утверждение о full LTO на весь WebRTC.

Собирать сразу четыре ABI в этой задаче не требуется. Подготовленный lab-профиль
ограничен `arm64-v8a`; телефон должен поддерживать эту ABI и Android API 23+.

## Инструменты: проверять версии явно

Проекту нужны полный JDK 17, Gradle 8.13, SDK 36, Build Tools 36.0.0,
NDK `27.2.12479018` и Android CMake `3.22.1`.
В Codex уже подготовлены полный Temurin JDK 17, Gradle 8.13 и Android
command-line tools, SDK 36, Build Tools 36.0.0, NDK 27.2.12479018,
CMake 3.22.1 и platform-tools. Все 16 arm64 archives догружены; BoringSSL
выгружен на закреплённом SHA для непосредственной Android-компиляции.
Полное локальное дерево submodules по-прежнему не разворачивалось.

Официальный snapshot образа Ubuntu 24.04 в `actions/runner-images`, commit
`67421cc1650a2ab8eac05d4674a787d25dc51627`, image `20261111.370.1`, содержит:

- JDK 17.0.21+9, SDK `android-36` revision 2 и Build Tools 36.0.0;
- NDK 27.3 по умолчанию, также версии 29/30;
- CMake 3.31.5/4.1.2;
- системный Gradle 9.9.1.

Поэтому нельзя заменить требуемый NDK 27.2 на default NDK 27.3 или использовать
системный Gradle вместо wrapper 8.13. NDK 27.2 и CMake 3.22.1 устанавливаются
явно. Образ обновляется; сохранять `ImageVersion`, Java/Gradle versions,
`sdkmanager --list_installed`, пути SDK и `df` конкретного job.
[Зафиксированный manifest runner image](https://github.com/actions/runner-images/blob/67421cc1650a2ab8eac05d4674a787d25dc51627/images/ubuntu/Ubuntu2404-Readme.md).

Label `ubuntu-24.04` выбран явно: `ubuntu-latest` в ноябре 2026 переводится на
Ubuntu 26.04. Версии внешних компонентов и action commit SHA должны быть
зафиксированы workflow; это не означает неизменяемость всей hosted VM.

## Checkout и локальное повторение

Для полной отдельной рабочей копии:

```bash
git clone --branch ci/ipv6-lab-apk-infrastructure \
  https://github.com/kkgpower/telegram-ipv6-lab.git ipv6-lab-ci
cd ipv6-lab-ci
git merge-base --is-ancestor e3bde6d2a7a2835ac2a36754c662dbc89715b160 HEAD
git submodule update --init --recursive
git submodule status --recursive
```

В существующем sparse checkout нужно дополнительно получить необходимые tracked
файлы. `git sparse-checkout disable` догружает полное дерево; сначала проверить
свободное место. Не выполнять `git submodule update --remote`: сборка использует
SHA, закреплённые superproject, а не текущие ветки сторонних проектов.

Инвентарь доступен без API; текущий ненулевой exit code означает перечисленные
недостающие prerequisites, включая API, а не результат Android-компиляции:

```bash
JAVA_HOME=/workspace/android-lab/tools/jdk-17 \
python3 tools/ipv6-lab/check-environment.py \
  --sdk /workspace/android-lab/sdk \
  --gradle /workspace/android-lab/tools/gradle-8.13/bin/gradle \
  --output /tmp/ipv6-lab-environment.json
```

Воспроизведение подготовки и проверок без API на runner с уже установленными
JDK 17 и Android command-line tools:

```bash
export JAVA_HOME=/workspace/android-lab/tools/jdk-17
export ANDROID_HOME=/workspace/android-lab/sdk
export GRADLE_BIN=/workspace/android-lab/tools/gradle-8.13/bin/gradle
export INFRA_REPORT_DIR=/tmp/ipv6-lab-infrastructure
export INFRA_ACCEPT_ANDROID_LICENSES=1
bash tools/ipv6-lab/prepare-infrastructure.sh
source "$INFRA_REPORT_DIR/infra-env.sh"
export INFRA_VERIFY_FULL_NATIVE=1
bash tools/ipv6-lab/verify-infrastructure.sh
```

`prepare` устанавливает только закреплённые версии, проверяет место и сохраняет
SDK revisions, required/optional submodules, все 16 `.a` и реальные ресурсы VM.
Полный checkout получается через `git sparse-checkout disable`, recursive
submodules — shallow и на pinned commits, без `--remote`. `verify` компилирует
реальный ConnectionSocket в Android ARM64 ELF, конфигурирует весь CMake-проект,
собирает `tgnet` и проверяет Gradle dependency metadata без `assemble` и без APK.
`INFRA_VERIFY_FULL_NATIVE=1` дополнительно собирает и линкует `tmessages.49` и
`twidget` с одним native worker; именно этот режим прошёл в третьем Actions run.
Успех dependency report не доказывает будущие artifact transforms/Java-компиляцию.

Для ограниченного локального диска можно сначала использовать
`INFRA_PREPARE_SOURCES=0` при подготовке и `INFRA_VERIFY_NATIVE_ONLY=1` при проверке.
Эти режимы явно помечаются `partial`/`android-translation-unit-only` и не означают
готовности всей сборки. Минимальный запас перед крупными стадиями — 4 ГиБ;
`INFRA_MIN_FREE_GIB` позволяет явно настроить его для своей машины.

В данном Codex у Java обнаружен `PKIX path building failed` для сертификата
управляемого proxy, хотя Python/curl получали официальный SDK catalog. Это
исправлено opt-in параметром:

```bash
export INFRA_JAVA_TRUSTSTORE=/etc/ssl/certs/java/cacerts
```

Используется существующее системное доверенное хранилище; проверка TLS не
отключается, сертификаты не выдумываются и глобальная Java-конфигурация не меняется.
Прокси берётся из унаследованного окружения. На обычном hosted runner этот
специфичный для Codex параметр не нужен. Если Gradle в Codex тоже идёт через proxy,
для него отдельно нужны штатные JVM proxy/trust properties; successful HTTP probe
не заменяет настоящий Gradle dependency check.

После подготовки SDK packages и получения собственных параметров используется
существующий `tools/ipv6-lab/build-apk.sh`; полный порядок приведён в
[инструкции lab APK](ipv6-lab-apk.md). Скрипт не должен подменять API, signer,
отсутствующие archives или submodule вымышленными значениями ради успешного exit.

## Запуск Actions без изменения master

Первый no-secrets запуск привязывается к `push` точной ветки
`ci/ipv6-lab-apk-infrastructure`. Это позволяет проверить workflow, инструментальную
цепочку и зависимости до появления API. У проверки нет доступа к подписывающим
secrets и нет задачи выпуска APK. Результаты локальных проверок нельзя выдавать
за уже состоявшийся запуск hosted runner.

Изменения только `docs/` не перезапускают тяжёлую проверку. Фильтры `paths` не
применяются к push тегов: явный `ipv6-lab-build-*` по-прежнему запускает workflow.
[Поведение path filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore).

Проверки выполняются в порядке: verified Gradle 8.13 → unit guards → 12 host
socket tests → 5 offline profile probes → SDK/submodules → Android native/CMake/
Gradle metadata. Поэтому ошибка тяжёлой инфраструктуры не скрывает уже доступные
быстрые проверки. В подписывающий job передаются Secrets только после успешной
проверки, в единственный build-step. Raw stdout/stderr подписанной Gradle-сборки
не попадает в Actions log; диагностический tail разрешён только no-secrets стадиям.

Непосредственная проверка исправления в Codex уже прошла: NDK r27c скомпилировал
`ConnectionSocket.cpp` за 1,17 с, заголовок результата проверен как AArch64 ELF
relocatable. Это не измерение длительности сборки Telegram. Результат —
[verification-report.json](ipv6-lab-ci-results/codex-current/verification-report.json).

Для будущей подписанной сборки предусмотрен отдельный push тега
`ipv6-lab-build-*`, указывающего на проверенный инфраструктурный коммит. Создание
такого тега — явный запрос сборки; оно не является релизом официального Telegram.
Например, после проверки SHA и настройки secrets:

```bash
git fetch origin ci/ipv6-lab-apk-infrastructure
git switch --detach origin/ci/ipv6-lab-apk-infrastructure
git rev-parse HEAD
git tag ipv6-lab-build-20261116-01 HEAD
git push origin refs/tags/ipv6-lab-build-20261116-01
```

Имя будущего тега должно быть новым; не переставлять уже использованный тег на
другой коммит. Ограничить допустимые refs подписывающего environment и проверять
происхождение коммита. Secrets не должны становиться доступны обычным branch/PR
проверкам, стороннему checkout или произвольному ref из внешнего ввода.

Для `workflow_dispatch` GitHub документирует требование наличия workflow в
default branch; UI-кнопка может отсутствовать для нашей отдельной ветки. Другая
формулировка docs допускает CLI/API dispatch после первого запуска, но до реальной
проверки на этом репозитории это не является обещанным способом запуска.
Push branch/tag документирован как работающий и для workflow, не объединённого
с default branch. Поэтому инструкция не требует merge в `master` ради UI.
[Push events и filters](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push),
[manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Подписывающие Secrets

Environment `ipv6-lab` должен содержать шесть отдельных GitHub Secrets:

| Secret | Назначение |
| --- | --- |
| `TELEGRAM_API_ID` | Собственный Telegram API ID |
| `TELEGRAM_API_HASH` | Собственный Telegram API hash |
| `LAB_KEYSTORE_BASE64` | Base64 настоящего собственного private-key keystore |
| `LAB_STORE_PASSWORD` | Пароль keystore |
| `LAB_KEY_PASSWORD` | Пароль private key |
| `LAB_KEY_ALIAS` | Alias private key |

`LAB_KEYSTORE` не является отдельным secret: это временный путь декодированного
файла на runner. Keystore создаётся с закрытыми правами и удаляется после job.
Secrets доступны только подписывающему job/step, не validation workflow.

Для уже созданного локального ключа использовать
`/workspace/android-lab/private/ipv6-lab.p12` и защищённый `signing.env`, не добавляя
их в Git. Для обновления существующего lab-приложения нужен прежний ключ. Создание
нового настоящего тестового ключа описано в `create-signing-key.py`; это не способ
получить сертификат Telegram. Ключ из репозитория и чужие API использовать нельзя.

Пример загрузки через GitHub CLI с интерактивным вводом API и паролей; команды
не содержат их значений:

```bash
gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab TELEGRAM_API_ID
gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab TELEGRAM_API_HASH
gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab LAB_STORE_PASSWORD
gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab LAB_KEY_PASSWORD
gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab LAB_KEY_ALIAS
base64 -w0 /workspace/android-lab/private/ipv6-lab.p12 | \
  gh secret set --repo kkgpower/telegram-ipv6-lab --env ipv6-lab LAB_KEYSTORE_BASE64
```

GitHub ограничивает отдельный secret размером 48 KB; Base64 увеличивает размер
исходного keystore. Проверить размер до загрузки, не выводя его содержимое.
Настройка Secrets и прав environment выполняется владельцем репозитория; workflow
сам не создаёт действительные API-параметры.
[Secrets reference](https://docs.github.com/en/actions/reference/security/secrets),
[создание environment secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

Нельзя передавать значения через shell tracing, печатать environment или сохранять
каталоги с ключами и generated BuildConfig в artifact/cache. Подписанный job должен
использовать allowlist выходных файлов: проверенный APK, SHA-256 и проверенные
публичные сведения о подписи/исходном SHA. Полный `assemble.log`, рабочий patch,
Gradle caches и private keystore не являются публичными диагностическими файлами.

API hash клиента неизбежно входит в APK. Secret masking защищает вывод CI, но не
скрывает hash от получателя APK. Загрузка APK в artifact публичного репозитория
означает его доступность пользователям с соответствующим доступом к artifacts;
не обещать секретность содержащихся внутри клиентских параметров.

## Время, хранение и доступность

Hosted job ограничен 6 часами; наш validation ограничен 180 минутами,
подписанная сборка — 300 минутами. Полный workflow может жить до 35 дней, включая
ожидание, но это не увеличивает время сборки одного job. Разделение проверок и
подписанной сборки не должно переносить секретные caches между ними.
[Actions limits](https://docs.github.com/en/actions/reference/limits).

Standard public compute бесплатен. Для private репозиториев и larger runners
действуют условия плана и биллинга владельца; larger runners оплачиваются и для
public repo. В текущих таблицах compute allowance выражается денежной суммой,
а не универсальным фиксированным числом минут. Artifact/cache storage учитываются
отдельно: GitHub Free включает 500 MB artifacts, стандартный cache allowance —
10 GB на репозиторий. Проверять действующий план и настройки, не обещая бесплатный
бесконечный срок хранения APK.
[Billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

По умолчанию artifacts/logs хранятся 90 дней; для public repo доступен срок 1–90
дней. Для тестовой сборки явно задаётся короткий срок хранения artifact.
[Retention settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
Сами Actions могут быть выключены или ограничены политиками репозитория/аккаунта;
подготовленный YAML не доказывает, что GitHub уже выделил runner и запустил job.

## Рекомендация и оставшиеся действия

1. Использовать стандартный public `ubuntu-24.04`: no-secrets validation с полным
   native compile/link уже прошёл, результаты сохранены. В Codex холодная полная
   сборка ограничена диском, и разворачивать оставшееся дерево здесь не рекомендуется.
2. После получения собственных API настроить environment Secrets, сохранить тот
   же локальный signer и запустить проверенный коммит через отдельный build tag.
3. Проверить package `org.kkgpower.telegram.ipv6lab.beta`, неофициальные имя/значок,
   arm64 ABI, подпись и SHA APK. Проверки Android/MTProto на телефоне остаются
   отдельным этапом; официальный Telegram удалять не требуется.
4. Если последующая APK-сборка исчерпает диск/RAM или timeout, перенести подписанный
   job на реально доступный более вместительный runner. Это решение принимается
   по измерениям неудачного запуска. Не менять IPv6 fix, DNS, версии библиотек
   или обычный профиль Telegram для маскировки инфраструктурной ошибки.
