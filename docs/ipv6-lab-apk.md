# Неофициальный IPv6 Lab APK

Дата проверки: 2026-11-15. Ветка: `fix/mtproto-proxy-ipv6-literal`.
Исходное исправление IPv6: `7f67b8a68803f32d72364f867694b2bfaef266ac`.

**APK пока не получен.** Реализован отдельный opt-in профиль сборки, подготовлены
JDK, Gradle, Android command-line tools и настоящий локальный тестовый ключ.
Пользовательские Telegram API ID/API hash будут предоставлены позднее; сборка
намеренно останавливается без них. SDK platform, Build Tools, NDK, CMake и полный
набор исходников ещё требуют подготовки. Android-компиляция и установка на телефон
не подтверждены. DNS и AAAA не изменены; с `master` ветка не объединялась.

## Что делает lab-профиль

Профиль включается только флагом `-PIPV6_LAB=true`. Без него сохраняется обычная
конфигурация проекта. Реализация — `tools/ipv6-lab/profile.gradle`, условные ветки
Gradle app/library, `BuildVars`, lab resources/manifest и изоляция runtime-сервисов.

- Конечный application ID фиксирован:
  **`org.kkgpower.telegram.ipv6lab.beta`**. Lab-режим не использует переопределение
  `APP_PACKAGE`: base ID задан в профиле, debug добавляет `.beta`. Java packages и
  namespace не переименовываются.
- Единственный app-вариант — `:TMessagesProj_App:assembleAfatDebug`, только
  **`arm64-v8a`**. Ограничение ABI применяется в app и нативной library. Huawei,
  standalone, HockeyApp и instrumented-test app-модули исключаются из settings
  при включённом lab-профиле; необходимые library/media modules остаются.
- Launcher имеет собственный значок и имя **IPv6 Lab (unofficial)**, включая
  активный alias `DefaultIcon`. Это не официальный Telegram.
- Provider authorities используют `${applicationId}`. AccountManager, contacts
  authenticator/sync adapter и account settings используют отдельный lab account
  type через `telegram_account_type` и `ApplicationLoader.getApplicationId()`.
- API передаются через environment, попадают в generated BuildConfig и выбираются
  в `BuildVars` только при `IPV6_LAB_BUILD`. Проверяются формат ID/hash и отказ от
  bundled-параметров. Никаких придуманных ключей для выпуска APK не используется.
- Подпись берётся из собственного keystore. Профиль проверяет private key и
  certificate и отвергает checked-in `release.keystore`, в том числе его копии
  с тем же содержимым. Сравниваются также сертификат и публичный ключ: перепаковка
  хранилища или перевыпуск сертификата с прежним ключом не обходят проверку.
  Объект конфигурации скрывает значения в `toString()`.
- Google services plugin не применяется ни в app, ни в library lab-варианта;
  собственный `google-services.json` для этого режима не нужен. Убраны
  FirebaseInitProvider, GCM service и Maps API key из lab manifest; push provider
  не регистрирует FCM. Google sign-in, FPNV, passkeys, SafetyNet и официальные
  обновления отключены. Штатная конфигурация Google Maps не используется;
  работоспособность карт и других сервисов Google в этом тестовом APK не заявляется.

Настройки упаковки не меняют исправление `ConnectionSocket.cpp`, значение
`isIpv6` конечного Telegram DC, DNS или AAAA. После предоставления собственных API
параметров следует отдельно проверить обычный login и передачу сообщений:
отсутствие FCM и Google-assisted login ограничивает доступные сценарии авторизации
и фоновых уведомлений.

## Инструменты и оставшиеся препятствия

| Компонент | Требуется / текущее состояние |
| --- | --- |
| Полный JDK | Установлен Temurin 17.0.21+9, `javac` и `jlink` проверены |
| JDK path | `/workspace/android-lab/tools/jdk-17` |
| Gradle | 8.13 загружен и проверен; `/workspace/android-lab/tools/gradle-8.13/bin/gradle` |
| Android command-line tools | 22.0 установлены в `/workspace/android-lab/sdk/cmdline-tools/22.0` |
| Android Gradle Plugin | Проект задаёт 8.13.2; полная AGP-конфигурация ещё не проверена |
| SDK platform | Требуется `platforms;android-36`, не установлен |
| Build Tools | Требуется `build-tools;36.0.0`, не установлен |
| NDK | Требуется `ndk;27.2.12479018`, не установлен |
| Android CMake | Требуется `cmake;3.22.1`, не установлен |
| Минимальный Android | API 23, Android 6.0 |
| Нативный C++ | C++17 |
| Platform Tools / adb | Установить для проверки и установки на устройство |
| Исходники и submodules | Checkout остаётся неполным; pinned submodules не инициализированы |
| Пользовательские API | Ожидаются, значения в репозиторий не записываются |
| Локальная подпись | Подготовлен собственный ключ вне checkout, см. ниже |

Проект также задаёт Kotlin Gradle Plugin 2.1.0, Google services plugin 4.5.0,
Firebase Crashlytics plugin 3.0.8 и Huawei AGConnect plugin 1.9.1.301. Несмотря на
отключение применения Google services в lab-модулях, root/buildSrc dependencies
должны разрешиться при конфигурации Gradle. Доступность Maven-зависимостей и
совместимость всех Gradle/AGP DSL проверяются фактическим запуском после подготовки
окружения, а не наличием файла Wrapper.

Официальный архив установленного Temurin JDK проверен по SHA-256:
`8b9b611d917e3dfd8419d3566b5949226f69b052fed7e109c1368add1dfe8711`.
Первоначальный Java 21 runtime не имел стандартного JDK layout; команда сборки
должна явно использовать подготовленный полный JDK 17.

На момент сохранённого inventory свободно около 6.3 GiB. Не инициализирован
21 top-level submodule, а 16 tracked arm64 native archives ещё отсутствуют в
sparse checkout. Наличие SDK/NDK не заменяет эти исходники и prebuilt. Необходимо
учесть распакованный NDK, полное дерево, Gradle/Maven cache и промежуточные native
артефакты; больший build environment или собственный CI может быть практичнее.
Сверять текущие ограничения RAM/CPU через cgroup, а не только host `free`/`nproc`.

Подробные результаты без секретов: [environment.json](ipv6-lab-results/environment.json),
[Gradle version](ipv6-lab-results/gradle-version.txt),
[SDK package metadata](ipv6-lab-results/sdk-packages.json).

## Собственная подпись и API

Создан настоящий локальный PKCS12 keystore:
`/workspace/android-lab/private/ipv6-lab.p12`. Его назначение — неофициальная
локальная тестовая подпись; это не сертификат Telegram. Каталог имеет mode 700,
keystore и `signing.env` — mode 600. Приватный ключ и пароли не входят в Git.

SHA-256 текущего публичного сертификата:
`f20e07db7fb30e7dfc8f79785ca390b99dfd400b7b32caa68e5f2adb1828a3b5`.
Сохранять этот ключ для последующих обновлений того же установленного lab-пакета.
Если выбран другой собственный ключ, проверять его фактический fingerprint.

Для новой среды ключ можно создать существующим helper, указав **новый** приватный
каталог вне репозитория. Существующие ключи helper не перезаписывает:

```bash
python3 tools/ipv6-lab/create-signing-key.py /workspace/new-ipv6-lab-private
```

`profile.gradle` и `build-apk.sh` требуют шесть environment variables:

| Имя | Назначение |
| --- | --- |
| `TELEGRAM_API_ID` | Собственный положительный 32-bit Telegram API ID |
| `TELEGRAM_API_HASH` | Собственный API hash, 32 hexadecimal characters |
| `LAB_KEYSTORE` | Путь к собственному keystore |
| `LAB_STORE_PASSWORD` | Пароль хранилища |
| `LAB_KEY_PASSWORD` | Пароль private key |
| `LAB_KEY_ALIAS` | Alias private key |

Первые два параметра получить через
<https://core.telegram.org/api/obtaining_api_id> и передать защищённой настройкой
окружения. Последние четыре экспортирует подготовленный приватный `signing.env`.
Не помещать значения в аргументы команд, Git, документацию или публикуемые логи.
Не включать shell tracing при загрузке environment. API hash клиентского
приложения окажется внутри собранного APK и не может считаться скрытым от его
владельца; исходные файлы и журналы всё равно не должны случайно раскрывать ввод.

## Подготовка дерева и Android packages

Для отдельной полной копии:

```bash
git clone --branch fix/mtproto-proxy-ipv6-literal \
  https://github.com/kkgpower/telegram-ipv6-lab.git ipv6-lab-build
cd ipv6-lab-build
git rev-parse HEAD
git merge-base --is-ancestor \
  7f67b8a68803f32d72364f867694b2bfaef266ac HEAD
git submodule update --init --recursive
git submodule status --recursive
```

В существующем sparse checkout дополнительно требуется
`git sparse-checkout disable`. Submodule должны оставаться на SHA, закреплённых
superproject; не использовать `git submodule update --remote`. Сохранить реальный
SHA lab-сборки и состояние submodule. Понадобятся также все tracked native/prebuilt
файлы, resources и локальные AAR/JAR, включая
`TMessagesProj/libs/libgsaverification-client.aar`.

После проверки свободного места установить Android packages и принять применимые
лицензии:

```bash
export JAVA_HOME=/workspace/android-lab/tools/jdk-17
export ANDROID_HOME=/workspace/android-lab/sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$PATH"
"$ANDROID_HOME/cmdline-tools/22.0/bin/sdkmanager" --sdk_root="$ANDROID_HOME" \
  'platform-tools' 'platforms;android-36' 'build-tools;36.0.0' \
  'ndk;27.2.12479018' 'cmake;3.22.1'
"$ANDROID_HOME/cmdline-tools/22.0/bin/sdkmanager" --sdk_root="$ANDROID_HOME" --licenses
```

Эти пакеты ещё не установлены в текущей среде; наличие команд в инструкции не
является результатом их выполнения. Команды могут требовать сетевого разрешения
облачного окружения. Размеры скачиваемых архивов сохранены в SDK metadata;
распакованные файлы и build outputs требуют дополнительного места.

## Запуск сборки

После подготовки зависимостей и предоставления API:

```bash
set +x
export JAVA_HOME=/workspace/android-lab/tools/jdk-17
export ANDROID_HOME=/workspace/android-lab/sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_BIN=/workspace/android-lab/tools/gradle-8.13/bin/gradle
export GRADLE_USER_HOME=/workspace/android-lab/gradle
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
source /workspace/android-lab/private/signing.env
# TELEGRAM_API_ID и TELEGRAM_API_HASH заранее заданы защищённой конфигурацией.
bash tools/ipv6-lab/build-apk.sh
```

Helper запускает `-PIPV6_LAB=true :TMessagesProj_App:assembleAfatDebug` с одним
worker и без parallel mode. Он проверяет наличие environment и полного JDK,
сохраняет inventory, вызывает Gradle, сохраняет настоящий exit code, проверяет
application ID, неофициальное имя, arm64 ABI и подпись APK против предоставленного
локального ключа. Положительный
результат `gradle --version`, синтаксического разбора или preflight не считается
успешной сборкой.

Результаты по умолчанию — `/tmp/telegram-ipv6-lab-apk-results`; переопределение —
`LAB_RESULT_DIR`. После успеха в каталоге появятся
`telegram-ipv6-lab-unofficial-arm64.apk`, `apk.sha256`, manifest/signature reports,
публичный сертификат, source commit и submodule state. Исходный APK варианта
ожидается в `TMessagesProj_App/build/outputs/apk/afat/debug/app.apk`.

Raw `assemble.log`, рабочий patch и остальные результаты создаются с приватным
umask. До проверки содержимого не публиковать полный build log или рабочий patch.
Приватные ключи и `signing.env` в каталог результатов не копируются.

## Проверки, уже выполненные

Реальные Android-компиляция, manifest merge, упаковка, установка и MTProto login
**не выполнялись**. Wrapper/Gradle и JDK запущены; отсутствующие API и Android
packages выявлены до полноценной сборки. Результат preflight хранится в
[apk-preflight.log](ipv6-lab-results/apk-preflight.log).

В isolated Gradle fixture без AGP выполнено **5/5 проверок**: обычный режим без
lab проходит; некорректный lab-флаг, отсутствующий environment, неверный API ID и
неверный формат hash корректно отклоняются. Для этих отказов не использовались
действительные пользовательские или придуманные пригодные для APK API-ключи.
Groovy parser разобрал app/library/profile scripts; lab XML разобраны XML parser.
Это не проверка Android DSL, manifest merger или доступности зависимостей.
Результаты сохраняются рядом с отчётом в [каталоге проверок](ipv6-lab-results/).

Повторить проверки самого профиля без Android SDK и без собственных API:

```bash
JAVA_HOME=/workspace/android-lab/tools/jdk-17 \
GRADLE_USER_HOME=/workspace/android-lab/gradle \
GRADLE_BIN=/workspace/android-lab/tools/gradle-8.13/bin/gradle \
python3 tools/ipv6-lab/test-profile.py
```

Они применяют реальный `profile.gradle` в минимальном временном Gradle-проекте.
Даже offline Gradle нужны локальные IPC sockets; в управляемом окружении это
может требовать сетевого разрешения песочницы. Лог —
[profile-probes.log](ipv6-lab-results/profile-probes.log).

Нативный harness находится в [tools/ipv6-lab/native-test](../tools/ipv6-lab/native-test/).
Он компилирует фактический `ConnectionSocket.cpp` и реальные buffer/TLS helpers;
подменена только инфраструктура Manager/EventObject/logging, а TCP и epoll настоящие.

| Транспортные сценарии | Результат |
| --- | --- |
| Числовые IPv4/IPv6 MTProto proxy, override и global settings | PASS, 4 |
| Прямые IPv4/IPv6 TCP подключения | PASS, 2 |
| SOCKS5, все четыре сочетания семейств proxy/DC с проверкой ATYP/address/port | PASS, 4 |
| Асинхронный ECONNREFUSED, закрытие FD и удаление из epoll, IPv4/IPv6 | PASS, 2 |
| Всего исправленная версия | 12/12 PASS |
| Исходная версия `21f7d109da6ab3506c9e9577f98c6a38771ab335`, IPv6 case | Ожидаемый FAIL: wrong actual socket family |

Логи: [исправленная версия](ipv6-lab-results/native-fixed.log),
[baseline](ipv6-lab-results/native-baseline.log). Повтор:

```bash
bash tools/ipv6-lab/native-test/build.sh
timeout 20s /tmp/telegram-ipv6-native-test-run/fixed-test
bash tools/ipv6-lab/native-test/build.sh --baseline
timeout 10s /tmp/telegram-ipv6-native-test-run/baseline-test 'MTProto IPv6 override'
```

Последняя команда должна завершиться с кодом 1. Проверки подтверждают host TCP
transport, включая socket family, sockaddr, O_NONBLOCK, TCP_NODELAY, epoll,
callbacks и двусторонние данные. Они не покрывают Android/JNI, Java DNS, настоящий
MTProto authentication/encryption или fake-TLS handshake.

## Проверка APK и безопасная отдельная установка

Этот раздел применим **после** успешного получения файла. Сейчас APK отсутствует.
Helper уже проверяет package и соответствие подписи; перед передачей на телефон
дополнительно сверить сохранённые SHA-256 и fingerprint:

```bash
APK_PATH=/tmp/telegram-ipv6-lab-apk-results/telegram-ipv6-lab-unofficial-arm64.apk
sha256sum "$APK_PATH"
"$ANDROID_HOME/build-tools/36.0.0/aapt" dump badging "$APK_PATH"
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose --print-certs "$APK_PATH"
adb devices
adb shell getprop ro.product.cpu.abilist
adb shell pm list packages org.kkgpower.telegram.ipv6lab.beta
adb install "$APK_PATH"
adb shell am start -n \
  org.kkgpower.telegram.ipv6lab.beta/org.telegram.ui.LaunchActivity
```

Телефон должен поддерживать `arm64-v8a` и API 23+. Первая установка выполняется
без `-r`: неожиданное существование такого package требует проверки предыдущего
lab-приложения и его подписи. Официальный Telegram не удалять. Последующие lab
обновления возможны с `adb install -r` после проверки package и того же ключа.
Не назначать lab обработчиком Telegram-ссылок по умолчанию; запускать явно.
Не копировать данные или авторизованную сессию официального клиента.

## Smoke test на телефоне

1. Проверить отдельные имя, значок и запуск lab и официального клиента. Убедиться,
   что package и системный account type lab изолированы. Для транспортного теста
   доступ к контактам не нужен.
2. Убедиться в наличии IPv6 адреса и маршрута на телефоне. Ввести числовой адрес
   доступного MTProto proxy **без квадратных скобок**, отдельный порт и действительный
   secret. Доменное имя в этот тест не включать.
3. Проверить доступность IPv6 proxy, затем IPv4 proxy. При предоставленных API
   проверить login и фактическую передачу сообщения через proxy.
4. Отключить proxy и проверить прямое соединение, затем повторное подключение
   после смены Wi-Fi/mobile network. SOCKS5 проверить отдельно при наличии сервера.
5. Записать Android version, ABI, SHA APK, certificate fingerprint, условия сети
   и результаты. Не публиковать API hash, secret proxy, login-коды, токены или
   личные сообщения в диагностике.

До выполнения этих шагов не заявлять об успешной установке или подтверждённой
работе исправления на Android-телефоне.
