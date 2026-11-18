# Character voices

Main characters only: one voice per character, kept the same in every book of a universe. When you write a book's `cast.json` (SKILL.md step 4), look each speaker up here first and use the listed voice. These entries override the "at most three female voices" rule. Side and minor characters are not listed; choose their voices per book with the SKILL.md step 3 rules.

- **Id** is the speaker id to use in `script.txt` and `cast.json`. The parser often splits one person into several ids (`Nguyệt`, `Mộc`, `Cơ`…); `RELABEL` them to this id during review.
- **Voice** is an onboarded Drama-3 id (`python3 -m viettts voice list`) or a VieNeu name. `narrator` means the MC shares the narrator voice.
- Add a character here only when they are a main character: they recur across books or carry a large part of one. Update the entry when the user changes their voice.
- **Books** lists the story folders (`img-prompts/stories/_archived/<folder>/story_vn.md`) where the character speaks.

## Sương Hỏa Cửu Chuyển Quyết (Thanh Vân Tông universe)

Narrator and MC: Hàn Thần (`ta`) on VieNeu **Thiện Minh**. Other men default to VieNeu **Hải Đăng**.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | Hàn Thần | `narrator` (Thiện Minh) | MC | shuangyue_v1–v5 |
| Sương Nguyệt | Nguyệt nhi, Tiểu Nguyệt, Sương Ma Nữ | `shirone-mika` | Heroine; bratty, possessive ice-cultivator sư muội | v1–v5 |
| Mộc Liên Hoa | Mộc trưởng lão | `tam-nee` | Hợp Hoan elder, wry schemer with lưu ảnh thạch | shuangyue_v4–v5, mahua_v4–v5 |
| Cơ Hồng Loa | Cơ tông chủ | `fuyuki-inari` | Hợp Hoan sect head, calm and dry | v4, v5 |
| Bạch Thanh Thanh | Liên Hoa Tiên Tử | `fuyuki-inari` | Thúy Liên Cốc healer, prim; engaged to Ngưu Mãnh | v3, v5 |
| Hỏa Linh | Hỏa Linh phu nhân | `fuyuki-inari` | Phoenix wife of Ngạo Côn, dry judge | v3, v5 |
| Đoạn Thanh | Đoạn Tình lão tổ; voice of the gate and lanterns of Uyên Ương Bí Cảnh | `tam-nee` | Weary ghost ancestor, v5's main antagonist | v5 |

## Khả Khả universe

Narrator and MC: Khả Khả's unnamed disciple (`ta`) on VieNeu **Thiện Minh**. Other men default to VieNeu **Hải Đăng**.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | đồ nhi, đồ đệ, tiểu tử | `narrator` (Thiện Minh) | MC; Khả Khả's disciple | keke_v1–v5 |
| Khả Khả | Tô Khả Khả, cô cô, sư phụ, lão cô cô | `lynasa` | Heroine; lazy, hedonistic Nguyên Anh elder fond of role-play | keke_v1–v5 |
| Trận Linh | trận linh Cửu Yên Luyện Cảnh, lão giữ cửa | Thùy Dung (VieNeu) | Male ancient trial spirit; dry, weary keeper of Khả Khả's sect memories | keke_v5 |

## Ma Hoa universe

Narrator and MC: Ma Hoa's unnamed sư đệ (`ta`) on VieNeu **Thiện Minh**. Other men default to VieNeu **Hải Đăng**.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | sư đệ, tiểu tử, dược liệu, đạo lữ, phu quân | `narrator` (Thiện Minh) | MC; Ma Hoa's unnamed junior disciple and partner | mahua_v1–v5 |
| Ma Hoa | Hoa sư tỷ, Ma đan sư, bánh quẩy nhỏ | `azu-livyatan` | Heroine; deadpan Hợp Hoan alchemist whose composure shifts selectively | mahua_v1–v5 |
| Bách Vị Tiên Nhân | gương mặt đá, vị tiên nhân, lão già | Hải Đăng | Deceased trial creator and voice of Bách Vị Bia | mahua_v3 |

## Mị Mị universe (Cầu Đạo Tông)

Narrator and MC: Lý Vân Chu (`ta`) on VieNeu **Thiện Minh**. Other men default to VieNeu **Hải Đăng**. `nina-meowmeow` takes light mood/attitude tags well; breath tags (`[panting]`, `[breathless]`, moans) make takes run past the frame cap.

Crossovers: v4 (meimei_v4) also has Khả Khả (`lynasa`, Khả Khả universe), Hỏa Linh and Cơ Hồng Loa (`fuyuki-inari`, Thanh Vân Tông universe) with their listed voices. Khả Khả's disciple, the narrator of his own books, uses Hải Đăng here (id `Đồ đệ Khả Khả`), since Thiện Minh is Lý Vân Chu.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | Lý Vân Chu, Vân Chu, Sư tôn, Phong chủ Vong Vân Phong | `narrator` (Thiện Minh) | MC; calm, honest Nguyên Anh sword master who indulges his disciple | meimei_v1–v6 |
| Mị Mị | Cố Niệm, đồ nhi, khôi thủ, Thánh nữ Vong Vân Phong; `female` in v1 | `nina-meowmeow` | Heroine; reincarnated game tester, lazy, lewd and scheming, plays the sweet disciple in public; in v5 split into three soul shards (all her, same voice); in v6 Cố Niệm in Trùng Khánh, speaks `tôi`/`anh` until she remembers | v1–v6 |
| Hoài Thanh | Đệ tử Hoài Thanh, đồ tôn of Đàm Trưởng lão | `nyan-mikuru` | Bách Thảo Đường inner disciple, earnest and naive; rescued from Xích Đỉnh Tông, calls Mị Mị "sư tỷ" | v3 |
| Hệ thống | Gia thần, the system panel / banners | Thùy Dung (VieNeu) | Mị Mị's game system. Its banners are narration lines in square brackets (`[MỞ KHÓA NHIỆM VỤ: …]`, `[TÌNH CẢM CỘNG HƯỞNG ↑] ▰▰▱…`); during review, answer each such line `Hệ thống` (`new: Hệ thống \| female` the first time). From v5 it also talks, in lowercase bracket lines (`[ta nói chuyện liên tục đấy chứ…]`), and in v6 through her old phone; the progress-bar line `▰▰▱…` is Hệ thống too | v3–v6 |
| Đàm Trưởng lão | Đàm (v2) | Hải Đăng | Bách Thảo Đường elder, grandfatherly, always fooled by Mị Mị's act | v1–v3, v5, v6 |
| Liễu lão thư lại | Liễu, họ Liễu, Liễu chưởng quỹ; `Liễu` in the parses | Adam bựa (VieNeu) | Important side character: vain, theatrical scribe of Thiên Mặc Đường in Hạ Trúc Cốc who writes popular romance stories | keke_v3, keke_v5, meimei_v4 |
