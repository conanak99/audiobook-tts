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
| Mộc Liên Hoa | Mộc trưởng lão | `tam-nee` | Hợp Hoan elder, wry schemer with lưu ảnh thạch | shuangyue_v4–v5, mahua_v4–v5, maomao_v4 |
| Cơ Hồng Loa | Cơ tông chủ | `fuyuki-inari` | Hợp Hoan sect head, calm and dry | v4, v5, maomao_v4, chunchun_v1 |
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
| Ma Hoa | Hoa sư tỷ, Ma đan sư, bánh quẩy nhỏ | `azu-livyatan` | Heroine; deadpan Hợp Hoan alchemist whose composure shifts selectively | mahua_v1–v5, maomao_v4 |
| Bách Vị Tiên Nhân | gương mặt đá, vị tiên nhân, lão già | Hải Đăng | Deceased trial creator and voice of Bách Vị Bia | mahua_v3 |

## Mị Mị universe (Cầu Đạo Tông)

Narrator and MC: Lý Vân Chu (`ta`) on VieNeu **Thiện Minh**. Other men default to VieNeu **Hải Đăng**. `nina-meowmeow` takes light mood/attitude tags well; breath tags (`[panting]`, `[breathless]`, moans) make takes run past the frame cap.

Crossovers: v4 (meimei_v4) also has Khả Khả (`lynasa`, Khả Khả universe), Hỏa Linh and Cơ Hồng Loa (`fuyuki-inari`, Thanh Vân Tông universe) with their listed voices. Khả Khả's disciple, the narrator of his own books, uses Hải Đăng here (id `Đồ đệ Khả Khả`), since Thiện Minh is Lý Vân Chu.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | Lý Vân Chu, Vân Chu, Sư tôn, Phong chủ Vong Vân Phong | `narrator` (Thiện Minh) for narration; dialogue `"mc": "thien-minh-drama"` from v3 (Drama-3 clone of Thiện Minh, so he can take tags: dry/deadpan/low directions) | MC; calm, honest Nguyên Anh sword master who indulges his disciple | meimei_v1–v6 |
| Mị Mị | Cố Niệm, đồ nhi, khôi thủ, Thánh nữ Vong Vân Phong; `female` in v1 | `nina-meowmeow` | Heroine; reincarnated game tester, lazy, lewd and scheming, plays the sweet disciple in public; in v5 split into three soul shards (all her, same voice); in v6 Cố Niệm in Trùng Khánh, speaks `tôi`/`anh` until she remembers | v1–v6 |
| Hoài Thanh | Đệ tử Hoài Thanh, đồ tôn of Đàm Trưởng lão | `nyan-mikuru` | Bách Thảo Đường inner disciple, earnest and naive; rescued from Xích Đỉnh Tông, calls Mị Mị "sư tỷ" | v3 |
| Hệ thống | Gia thần, the system panel / banners | Thùy Dung (VieNeu) | Mị Mị's game system. Its banners are narration lines in square brackets (`[MỞ KHÓA NHIỆM VỤ: …]`, `[TÌNH CẢM CỘNG HƯỞNG ↑] ▰▰▱…`); during review, answer each such line `Hệ thống` (`new: Hệ thống \| female` the first time). From v5 it also talks, in lowercase bracket lines (`[ta nói chuyện liên tục đấy chứ…]`), and in v6 through her old phone; the progress-bar line `▰▰▱…` is Hệ thống too | v2–v6 |
| Đàm Trưởng lão | Đàm (v2) | Hải Đăng | Bách Thảo Đường elder, grandfatherly, always fooled by Mị Mị's act | v1–v3, v5, v6 |
| Liễu lão thư lại | Liễu, họ Liễu, Liễu chưởng quỹ; `Liễu` in the parses | `adam-bua-drama` (Drama-3) | Important side character: vain, theatrical scribe of Thiên Mặc Đường in Hạ Trúc Cốc who writes popular romance stories | keke_v3, keke_v5, meimei_v4, maomao_v1–v2 |

## Lý Miêu Miêu universe (Cầu Đạo Tông, maomao)

Narrator and MC: the unnamed ngoại môn phụ bếp (`ta`) on VieNeu **Hải Đăng** for narration; his dialogue is `"mc": "hai-dang-drama"` (Drama-3 clone of Hải Đăng, so he takes dry/low/deadpan directions). Other men use VieNeu **Thiện Minh**, since Hải Đăng is the narrator. Liễu lão thư lại (listed under the Mị Mị universe) uses `adam-bua-drama` here too, with tags. Breath tags on Miêu Miêu occasionally hit the frame cap; the build falls back to plain for those lines.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | sư đệ, tên tạp dịch, tên bếp phó, tên phụ bếp ngoại môn | `narrator` (Hải Đăng) for narration; dialogue `"mc": "hai-dang-drama"` | MC; reincarnated backend engineer turned calm, dry kitchen hand who "blackmails" Miêu Miêu | maomao_v1–v5 |
| Miêu Miêu | Lý Miêu Miêu, Tiểu Ma Nữ, bản ma nữ, sư tỷ; `Vệt` in the v1 parse | `shirone-mika` | Heroine; bratty, haughty 18-year-old Kim Đan prodigy of Vong Vân Phong who craves being dominated | maomao_v1–v5 |
| Mị Mị | Mị Mị phu nhân, mẫu thân | `nina-meowmeow` | Miêu Miêu's gamer-mother (transmigrator from Earth); cheeky, teasing, speaks in game slang. Same voice as the Mị Mị universe | maomao_v3–v5 |
| Lý Vân Chu | Vân Chu, Phong chủ, phụ thân | `thien-minh-drama` | Miêu Miêu's father, stern, dry sword master; appears briefly in v3–v4, and has a large part in v5. Same voice as the Mị Mị universe | maomao_v3–v5 |

## Vu Xuân Quyển universe (Hàn Sơn Phong, chunchun)

Narrator and MC: Hàn Lập (`ta`) on VieNeu **Hải Đăng** for narration; his dialogue is `"mc": "hai-dang-drama"`. Other men use VieNeu **Thiện Minh**, since Hải Đăng is the narrator. Sương Nguyệt (his mother), Ma Hoa (called Ma di) and Cơ Hồng Loa keep their voices from the other universes. Tô Khả Khả is on `pong-kyubi` in this universe, not `lynasa`, so she does not sound like Tiểu Xuân.

| Id | Also called | Voice | Who | Books |
|---|---|---|---|---|
| ta | Hàn Lập, Lập sư đệ, Lập nhi, tiểu tử rùa | `narrator` (Hải Đăng) for narration; dialogue `"mc": "hai-dang-drama"` | MC; cunning formation master of Hàn Sơn Phong, son of Hàn Thần and Sương Nguyệt | chunchun_v1 |
| Tiểu Xuân | Vu Xuân Quyển, Xuân Xuân, Tiểu Xuân, nem cuốn | `lynasa` | Heroine; loud, hot-headed body-cultivator of Yên Vân Phong, Tô Khả Khả's disciple, treats everything as a duel | chunchun_v1 |
| Sương Nguyệt | Sương Nguyệt phu nhân, mẫu thân | `shirone-mika` | MC's mother here; same voice as the Thanh Vân Tông universe | chunchun_v1 |
| Ma Hoa | Ma di, Ma Hoa di | `azu-livyatan` | Tiểu Xuân's alchemist mother; same voice as the Ma Hoa universe | chunchun_v1 |
| Khả Khả | Tô Khả Khả, Tô Khả Khả Đại, Tô trưởng lão, sư phụ | `pong-kyubi` | Tiểu Xuân's master; boisterous, lewd Yên Vân Tông elder (id `Tô Khả Khả Đại` in v1, `Khả Khả` in v2) | chunchun_v1–v2 |
| Vu thúc | Vu thúc | Đức Trí (VieNeu) | Tiểu Xuân's father, Ma Hoa's husband; huge, gentle and resigned | chunchun_v2 |
| Diệp Nhi | Ngao Chu Diệp, tiểu nha đầu rồng phượng | `nyan-mikuru` | Daughter of Ngạo Côn (Chân Long) and Hỏa Linh (Chân Phượng); lonely 18-year-old Nguyên Anh child-like dragon who calls Hàn Lập her toy. Will become a female MC in another series, so keep this voice | chunchun_v5 |
| Hỏa Linh | Hỏa Linh phu nhân | `fuyuki-inari` | Phoenix mother of Diệp Nhi, dry judge; same voice as the Thanh Vân Tông universe | chunchun_v5 |
| Ngạo Côn | Chân Long | Đức Trí (VieNeu) | Boisterous dragon father of Diệp Nhi; Hàn Thần's old rival | chunchun_v5 |
| Vinh Điệp | Vinh Điệp (danh đào) | `ngoc-trinh` | Stern, flamboyant director of the Hí Cảnh Phường theatre (Hợp Hoan Phong); smokes a pipe, dresses Tiểu Xuân for 《Hồ Ly Tế Ty》 | chunchun_v4, chunchun_v6 |
| Lộc Lộc | Tô Lộc Lộc, tiểu sư muội | `pong-kyubi` | Tiểu Xuân's lazy, sleepy junior sister, Tô Khả Khả's disciple; will be a female lead in another series, so keep this voice | chunchun_v6 |
| Mộc Liên Hoa | Mộc | `tam-nee` | Hợp Hoan elder who scores the khảo hạch (voice per the Thanh Vân Tông universe) | chunchun_v4 |
| Bạch Thanh Thanh | Bạch trưởng lão | `fuyuki-inari` | Prim healer of Thúy Liên Cốc (voice per the Thanh Vân Tông universe) | chunchun_v6 |
