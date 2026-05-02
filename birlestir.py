import os


def klasoru_txt_yap(kaynak_dizin, cikti_dosyasi):
    # İstemediğimiz veya okunamayacak formatları filtreleyelim
    istenmeyen_uzantilar = ('.png', '.jpg', '.jpeg', '.pyc', '.zip', '.gz', '.tar', '.pdf', '.exe')
    istenmeyen_klasorler = ('__pycache__', '.git', '.idea', 'venv', 'node_modules')

    with open(cikti_dosyasi, 'w', encoding='utf-8') as out_file:
        for root, dirs, files in os.walk(kaynak_dizin):
            # İstenmeyen klasörleri atla
            dirs[:] = [d for d in dirs if d not in istenmeyen_klasorler]

            for file in files:
                # İstenmeyen veya gizli dosyaları atla
                if file.endswith(istenmeyen_uzantilar) or file.startswith('.'):
                    continue

                dosya_yolu = os.path.join(root, file)
                goreceli_yol = os.path.relpath(dosya_yolu, kaynak_dizin)

                # Claude'un dosyaları ayırması için belirgin bir başlık atıyoruz
                out_file.write(f"\n{'=' * 60}\n")
                out_file.write(f"DOSYA: {goreceli_yol}\n")
                out_file.write(f"{'=' * 60}\n\n")

                try:
                    with open(dosya_yolu, 'r', encoding='utf-8') as in_file:
                        out_file.write(in_file.read())
                        out_file.write("\n")
                except UnicodeDecodeError:
                    out_file.write("[UYARI: Bu dosya metin tabanlı değil veya okunamadı.]\n")

    print(f"✅ Harika! Tüm kodların '{cikti_dosyasi}' adında tek bir dosyada birleştirildi.")


# Çalıştırmak için:
# 1. Parametre: Okunacak klasörün yolu ('.' demek bulunduğu klasör demektir)
# 2. Parametre: Oluşturulacak txt dosyasının adı
klasoru_txt_yap('.', 'claude_icin_kodlar.txt')