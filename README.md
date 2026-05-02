# mkk_auth — Modular Authentication Library (Python Reference Implementation)

> **Bu Python paketi bir referans implementasyondur.** Production sürümü Java/Spring ile yazılacak. Buradaki amaç:
> 1. Mimariyi somutlaştırmak
> 2. Java geliştiricisine "sınıf yapısı şu, akış böyle" diye spec göstermek
> 3. JSON policy + provider injection + zorunlu logging yapısının çalıştığını kanıtlamak

## Hızlı Bakış — 30 saniyede çalıştır

```bash
tar -xzf mkk_auth_demo_v3.tar.gz
cd mkk_auth_demo
pip install -r requirements.txt
python app.py
```

Tarayıcıda aç: **http://localhost:5000**

3 sayfa var:
- `/` → **Builder** (drag-drop akış oluştur)
- `/execute` → **Test Sayfası** (akışı gerçek bir login simülasyonuyla çalıştır)
- `/test-users` → **Test Kullanıcıları** (hangi kullanıcı/şifre/TCKN var)

## İş Akışı

1. **Builder'da** akış oluştur (örn. "userpass → SMS OTP")
2. **🚀 Gerçek Test (Execute)** butonuna bas → yeni sekmede test sayfası açılır
3. Test sayfasındaki form ile akışı **gerçekten çalıştır** — sağdaki test kullanıcılarından kopyala
4. Alttaki **canlı log paneli** her adımda kütüphanenin neyi loglamadığını gösterir

Builder'a girmeden test yapmak istersen:
- `/execute` → "Hazır policy seç" dropdown'ından birini seç
- veya "📁 JSON Yükle" ile elindeki bir JSON'u yükle

## Hızlı Bakış — Sadece Python (Flask'sız)

```bash
tar -xzf mkk_auth_demo_v3.tar.gz
cd mkk_auth_demo
python examples/01_aracikurum.py
python examples/run_policy.py policies/01_aracikurum.json
```

Bağımlılık YOK. Sadece Python 3.10+ gerekli.

## Demo akışı: builder ↔ kütüphane

```
   ┌─────────────────────┐                    ┌──────────────────────┐
   │  flow_builder.html  │  → JSON export →   │  mkk_auth library    │
   │  (drag-drop)        │                    │  (engine + stages)   │
   └─────────────────────┘                    └──────────────────────┘
            ↓                                            ↓
       [PNG export]                              [run_policy.py runner]
       Confluence'a                              Terminal'de canlı çalışır
```

**Sunumda göstereceğin demo:**
1. `flow_builder.html`'de yeni bir akış kur
2. JSON export et → kaydet (örn. `policies/yeni_akis.json`)
3. `python examples/run_policy.py policies/yeni_akis.json`
4. Terminal seni adım adım yönlendirir, akış canlanır

JSON'da değişiklik yaptığında kod hiç değişmez — sadece JSON yeterli.

## Project Layout

```
mkk_auth_demo/
├── README.md
├── mkk_auth/                     ← Asıl kütüphane
│   ├── engine.py                 (AuthEngine — orkestratör)
│   ├── policy.py                 (JSON policy parser)
│   ├── context.py                (AuthContext — session state)
│   ├── state.py                  (AuthState, StageResult, enum'lar)
│   ├── stages/                   (17 yerleşik stage)
│   ├── providers/                (interface'ler + in-memory impl)
│   └── logging/                  (AuthLogger + 6 implementation)
│
├── examples/                     ← Tek tek demolar
│   ├── 01_aracikurum.py          MERSIS → temsilci seç → SMS OTP
│   ├── 02_paralel.py             TCKN → [SMS | Email] paralel
│   ├── 03_userpass_tckn.py       TCKN + şifre tek adımda
│   ├── 04_uc_faktor.py           3-faktör (4 senaryo)
│   ├── 05_lockout.py             Rate limiter ile kilit
│   ├── 06_edevlet.py             e-Devlet redirect
│   ├── 07_captcha_ldap.py        Image captcha + LDAP
│   └── run_policy.py             ⭐ UNIVERSAL RUNNER
│
└── policies/                     ← Builder'dan JSON export'lar
    ├── 01_aracikurum.json
    ├── 02_paralel.json
    ├── 03_userpass_tckn.json
    ├── 04_uc_faktor.json
    ├── 05_edevlet.json
    ├── 06_captcha_ldap.json
    └── 07_gib_tarzi.json
```

## Kullanım

### main.py'da çağırmak

```python
from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import InMemoryLookupProvider, InMemoryOOBChannel

engine = AuthEngine.from_policy(
    "policies/01_aracikurum.json",
    providers={
        "lookup": InMemoryLookupProvider(MERSIS_DATA),
        "sms":    InMemoryOOBChannel(),
    },
    logger=LoggerFactory.console(),
)

state = engine.start(form_data={"s_0_0_in": "0123456789012345"})
```

### Universal Runner (sunumun yıldızı)

```bash
python examples/run_policy.py policies/04_uc_faktor.json
```

Runner:
- JSON'u okur, hangi provider'ların gerektiğini görür
- Mock provider'ları otomatik kurar
- Her stage için doğru input'u sorar
- SMS/Email kodlarını konsola yazdırır
- Push'u "Enter=onayla, r=reddet" ile sahneler
- e-Devlet redirect'ini gösterir

### Flask'a bağlama

```python
@app.route("/login", methods=["POST"])
def login():
    state = engine.start(form_data=request.form)
    return _render_state(state)

@app.route("/login/<sid>", methods=["POST"])
def login_continue(sid):
    state = engine.resume(sid, form_data=request.form)
    return _render_state(state)
```

## Logging — ZORUNLU

`AuthEngine` constructor'ında `logger` parametresi **zorunlu**. Geçemezsin — `LoggerRequiredError` fırlatır. `NoOpLogger` da reddedilir.

| Logger              | Kullanım                                  |
|---------------------|-------------------------------------------|
| `ConsoleLogger`     | Geliştirme — stdout'a renkli çıktı        |
| `JsonFileLogger`    | CI/test — JSONL formatında dosyaya yazar  |
| `InMemoryLogger`    | Unit testler — events listesinde tutar    |
| `GraylogGelfLogger` | Production — UDP GELF                     |
| `CompositeLogger`   | Birden fazla logger'ı birleştirir         |

**Java production tarafı:** Logback'in GELF appender'ı ile Graylog stream'e log atar.

### Log event tipleri

| event_type              | Ne zaman                                 | Severity |
|-------------------------|------------------------------------------|----------|
| `engine.start`          | Yeni session başladı                     | INFO     |
| `engine.ready`          | Engine başarıyla kuruldu                 | INFO     |
| `step.start`            | Yeni adıma geçildi                       | INFO     |
| `stage.success`         | Stage başarılı                           | INFO     |
| `stage.failed`          | Yanlış input                             | WARN     |
| `stage.lockout`         | Stage maxRetries aşıldı                  | CRITICAL |
| `step.expired`          | Shared timer doldu                       | CRITICAL |
| `oob.code_sent`         | OTP gönderildi (alıcı maskeli)           | INFO     |
| `provider.lookup`       | Dış sistem sorgusu                       | INFO     |
| `external_idp.redirect` | e-Devlet/GIB'e yönlendirildi             | INFO     |
| `external_idp.callback` | Provider'dan dönüş geldi                 | INFO     |
| `push.sent` / `.approved` / `.rejected` | Push akışı           | INFO/WARN|
| `session.success`       | Akış tamamlandı                          | INFO     |
| `session.locked`        | RateLimiter kullanıcıyı engelledi        | CRITICAL |

**PII maskeleme:** TCKN, telefon, e-posta log'da maskeli (`12345678901` → `123******01`).

## Stage Türleri (17 yerleşik)

| Kategori | Stage type             | Açıklama                              |
|----------|------------------------|---------------------------------------|
| identify | `mersis_lookup`        | MERSIS sorgu                          |
| identify | `tckn_standalone`      | TCKN sorgu                            |
| identify | `generic_lookup`       | Konfigüre edilebilir dış sorgu        |
| verify   | `field_match`          | Listede alan eşleştirme               |
| verify   | `representative_select`| Listeden seç                          |
| verify   | `captcha`              | reCAPTCHA / Turnstile                 |
| verify   | `image_captcha`        | Resim captcha                         |
| deliver  | `sms_oob`              | SMS OTP                               |
| deliver  | `email_oob`            | Email OTP                             |
| auth     | `userpass`             | Identifier+şifre (11 identifier tipi) |
| auth     | `ldap`                 | LDAP/AD bind                          |
| auth     | `totp`                 | Authenticator kodu                    |
| auth     | `esign`                | e-İmza (USB token)                    |
| auth     | `mobile_sign`          | Mobil imza (operatör)                 |
| auth     | `push_approve`         | Push onay                             |
| auth     | `mobile_authenticator` | Tap-the-number                        |
| auth     | `external_idp`         | e-Devlet/GIB/Google redirect          |

`userpass` identifier tipleri: username, tckn, vkn, sicil, uye_no, yatirimci_no, passport, vergi_no, hesap_no, iban, email, custom.

## Provider Eşleşmeleri

| Python Protocol         | Java interface                 | Production'da kim?     |
|-------------------------|--------------------------------|------------------------|
| `LookupProvider`        | `interface LookupProvider`     | Oracle DB sorgu        |
| `OOBChannel`            | `interface OOBChannel`         | NetGSM SMS API         |
| `CredentialStore`       | `interface CredentialStore`    | Oracle pwd hash        |
| `LdapProvider`          | `interface LdapProvider`       | Active Directory       |
| `SessionStore`          | `interface SessionStore`       | Redis                  |
| `RateLimiter`           | `interface RateLimiter`        | Redis sliding window   |
| `PushProvider`          | `interface PushProvider`       | FCM / APNS             |
| `ExternalIdpProvider`   | `interface ExternalIdpProvider`| e-Devlet OAuth         |
| `ESignProvider`         | `interface ESignProvider`      | Java applet + cert     |
| `MobileSignProvider`    | `interface MobileSignProvider` | Operatör (TT/VF/TC)    |

## Java'ya Çeviri Tablosu

| Python                           | Java                                       |
|----------------------------------|--------------------------------------------|
| `class BaseStage(ABC)`           | `public abstract class BaseStage`          |
| `@abstractmethod def evaluate()` | `public abstract StageResult evaluate(...)`|
| `class XxxProvider(Protocol)`    | `public interface XxxProvider`             |
| `@dataclass class StageResult`   | `public record StageResult(...)`           |
| `class StageStatus(Enum)`        | `public enum StageStatus`                  |
| `from_config(config, providers)` | constructor + `@Autowired`                 |
| `Optional[dict]`                 | `Optional<Map<String,Object>>`             |
| `dict[str, Any]`                 | `Map<String, Object>`                      |
| `pickle.dumps(ctx)`              | Jackson serialization                      |

## Veritabanı?

**Yok.** Kütüphane DB'ye bağlanmaz. Provider'lar interface — uygulama implementasyonunu yapar.

## Sunum Senaryosu (5 dakika)

**1 dk — Problem**: 10 farklı uygulama, 10 farklı login kodu.

**2 dk — Çözüm**: `flow_builder.html`'de akış kur, JSON export.

**3 dk — Çalışan kod**:
```bash
python examples/run_policy.py policies/04_uc_faktor.json
```

**4 dk — Yeni akış 1 dakikada**: JSON'u editle (ör. `maxRetries: 3 → 1`), tekrar çalıştır.

**5 dk — Java translation**: README'deki çeviri tablosunu göster.

## Komutlar

```bash
# Tek tek demolar
python examples/01_aracikurum.py
python examples/02_paralel.py
python examples/03_userpass_tckn.py
python examples/04_uc_faktor.py
python examples/05_lockout.py
python examples/06_edevlet.py
python examples/07_captcha_ldap.py

# Universal runner
python examples/run_policy.py policies/01_aracikurum.json
python examples/run_policy.py /path/to/builder_export.json
```
