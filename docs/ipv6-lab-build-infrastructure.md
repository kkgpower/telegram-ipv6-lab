# Инфраструктура сборки IPv6 Lab APK

Проверено 2026-11-16. База — `e3bde6d2a7a2835ac2a36754c662dbc89715b160`,
ветка инфраструктуры — `ci/ipv6-lab-apk-infrastructure`. Эта работа не требует
слияния с `master` или изменения исходного IPv6-исправления, DNS и обычной
конфигурации Telegram. Собственные Telegram API ID/API hash пока отсутствуют.
**APK не выпущен.** Подготовленный workflow и состоявшийся запуск CI — разные
результаты; сведения о фактических запусках следует проверять по журналам Actions.

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

Для public-репозитория стандартный Actions runner даёт больше CPU/RAM, чем
текущий Codex, и является предпочтительным первым кандидатом для полной arm64
сборки. Достаточность его ресурсов ещё должна быть подтверждена фактической
сборкой. Текущее облачное окружение подходит для анализа, host-тестов и подготовки
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

В CMake включены debug information и full LTO; native link может потребовать
существенной памяти. Один Gradle worker и arm64-only уменьшают нагрузку, но не
доказывают, что все этапы поместятся в 8 ГиБ. Время и пик RSS полной сборки пока
не измерены. Не следует представлять предполагаемые размеры intermediates как
проверенный факт или обещать завершение в лимит hosted job.

Собирать сразу четыре ABI в этой задаче не требуется. Подготовленный lab-профиль
ограничен `arm64-v8a`; телефон должен поддерживать эту ABI и Android API 23+.

## Инструменты: проверять версии явно

Проекту нужны полный JDK 17, Gradle 8.13, SDK 36, Build Tools 36.0.0,
NDK `27.2.12479018` и Android CMake `3.22.1`.
В Codex уже подготовлены полный Temurin JDK 17, Gradle 8.13 и Android
command-line tools. Остальные компоненты и checkout проверяются отдельно.

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

Hosted job ограничен 6 часами; полный workflow может жить до 35 дней, включая
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

1. Выполнить no-secrets validation в стандартном public `ubuntu-24.04`, сохранить
   версии, состояние checkout, расход диска/памяти и настоящий итог job.
2. Исправлять только подтверждённые препятствия инфраструктуры. Не менять версии
   native-библиотек, IPv6 fix или DNS для маскировки проблем checkout/toolchain.
3. После получения собственных API настроить environment Secrets, сохранить тот
   же локальный signer и запустить проверенный коммит через отдельный build tag.
4. Проверить package `org.kkgpower.telegram.ipv6lab.beta`, неофициальные имя/значок,
   arm64 ABI, подпись и SHA APK. Проверки Android/MTProto на телефоне остаются
   отдельным этапом; официальный Telegram удалять не требуется.
5. Если полный native link исчерпает диск/RAM или 6 часов, перенести подписанный
   job на реально доступный более вместительный runner. Это решение принимается
   по измерениям неудачного запуска, а не по предположению об успешной сборке.
