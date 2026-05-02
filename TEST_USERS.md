# Test Kullanıcıları

Aşağıdaki kullanıcılar `test_credentials.yaml` dosyasından gelir ve Flask uygulaması tarafından mock provider'lara yüklenir.

> **Not:** Bu sadece test/demo için. Production'da bu dosya olmayacak — gerçek veri Oracle/LDAP'tan gelecek.

---

## 🔑 Username + Password

| Kullanıcı | Şifre | Telefon | Email | Rol |
|-----------|-------|---------|-------|-----|
| `emrecan` | `test1234` | 05321234567 | emrecan@mkk.com.tr | admin |
| `ali` | `ali5678` | 05332345678 | ali@mkk.com.tr | user |

---

## 🆔 TCKN + Şifre

| TCKN | Şifre | İsim | Telefon |
|------|-------|------|---------|
| `11111111110` | `tckn1234` | Emrecan Bayhan | 05321234567 |
| `22222222220` | `tckn5678` | Ali Yılmaz | 05332345678 |

---

## 🏢 VKN + Şifre

| VKN | Şifre | Şirket |
|-----|-------|--------|
| `1234567890` | `vkn1234` | Demo Ticaret A.Ş. |

---

## 📋 Sicil No + Şifre

| Sicil | Şifre | İsim |
|-------|-------|------|
| `001234` | `sicil12` | Emrecan Bayhan |

---

## 🛂 Passport (Yabancı Yatırımcı)

| Passport | Şifre | İsim | Ülke |
|----------|-------|------|------|
| `U12345678` | `pass1234` | John Smith | USA |

---

## 🏛 MERSIS (Şirket Sorgusu)

### Çift temsilcili
**MERSIS:** `0123456789012345`
**Şirket:** Acme Aracı Kurum A.Ş.

| Temsilci | TCKN | Sicil | Telefon |
|----------|------|-------|---------|
| Emrecan Bayhan | `11111111110` | 001234 | 05321234567 |
| Ali Yılmaz | `22222222220` | 005678 | 05332345678 |

### Tek temsilcili (auto-skip test için)
**MERSIS:** `9876543210987654`
**Şirket:** Beta Holding A.Ş.

| Temsilci | TCKN | Telefon |
|----------|------|---------|
| Veli Demir | `33333333330` | 05551234567 |

---

## 🌐 LDAP / Active Directory

| Kullanıcı | Şifre | DN |
|-----------|-------|-----|
| `ldapuser` | `ldap1234` | cn=ldapuser,ou=users,dc=mkk,dc=local |
| `ldapadmin` | `admin123` | cn=ldapadmin,ou=admins,dc=mkk,dc=local |

---

## 🔐 Diğer

### TOTP
Demo modunda **`000000` dışında herhangi 6 haneli kod** kabul edilir.

### Captcha (reCAPTCHA tarzı)
Demo modunda **herhangi bir değer** kabul edilir.

### Image Captcha
Kütüphane kod üretir ve sayfada gösterir. **Aynen kopyala** — büyük/küçük harf duyarsız.

### e-İmza
Demo modunda **`0000` dışında 4+ haneli herhangi PIN** kabul edilir.

### Mobil İmza
Demo modunda telefonda otomatik onay simülasyonu.

### Push Approve
Demo'da **"Onayla"** butonu sayfada görünür → bas.

### e-Devlet / GIB Redirect
Demo'da provider'a yönlendirme simüle edilir, hemen "geri döner" gibi davranır.

---

## SMS / Email Kodları

`sms_oob` ve `email_oob` stage'lerinin kodları **gerçekten gönderilmez**. Konsola/log paneline yazdırılır:

```
📱 [SMS]   05321234567: 472891
✉  [EMAIL] emrecan@mkk.com.tr: 856421
```

Test ekranındaki **canlı log paneli**nde bu satırı görüp kodu kopyalayabilirsin.
