# Character voices

All the books share one universe: the same character keeps the same voice in every series. When you write a book's `cast.json` (SKILL.md step 4), set the series roles from **Series** first, then look each speaker up in **Characters**. These entries override the "at most three female voices" rule. Side and minor characters are not listed; choose their voices per book with the SKILL.md step 3 rules.

- **Id** is the speaker id to use in `script.txt` and `cast.json`. The parser often splits one person into several ids (`Nguyệt`, `Mộc`, `Cơ`, `Chu Diệp`…); `RELABEL` them to this id during review.
- **Canon** is the character's voice: an onboarded Drama-3 id (`python3 -m viettts voice list`) or a VieNeu name. For an MC it is narration / dialogue (`Thiện Minh` / `thien-minh-drama`).
- **Fallback** is used only in a book where the canon voice is already taken by someone who speaks in the same scenes (usually that book's MC or narrator). It applies to that book only; the next book goes back to canon. If the fallback is also taken, pick a free voice of the same style, tell the user, and add it here.
- Add a character only when they are a main character: they recur across books or carry a large part of one. Update the entry when the user changes a voice, and record a new fallback when you use one.
- **Books** lists the story folders (`img-prompts/stories/_archived/<folder>/story_vn.md`) where the character speaks.

## Series

The narrator and MC roles per series. `mc` is the MC's dialogue (Drama-3 so it takes `enhance.txt` tags); `male` is every other man. Pick `male` so it doesn't share a timbre with a listed man in the book.

| Series | Folder | `narrator` | `mc` | `male` | Notes |
|---|---|---|---|---|---|
| Sương Hỏa Cửu Chuyển Quyết | shuangyue | Thiện Minh | Thiện Minh | Hải Đăng | MC Hàn Thần |
| Khả Khả | keke | Thiện Minh | Thiện Minh | Hải Đăng | MC Khả Khả's disciple |
| Ma Hoa | mahua | Thiện Minh | Thiện Minh | Hải Đăng | MC Ma Hoa's sư đệ |
| Mị Mị | meimei | Thiện Minh | `thien-minh-drama` (from v3) | Hải Đăng | MC Lý Vân Chu. `nina-meowmeow` takes light mood tags well; breath tags hit the frame cap |
| Lý Miêu Miêu | maomao | Hải Đăng | `hai-dang-drama` | Thiện Minh | MC Bếp Trưởng. Breath tags on Miêu Miêu occasionally fall back to plain |
| Vu Xuân Quyển | chunchun | Hải Đăng | `hai-dang-drama` | Thiện Minh | MC Hàn Lập |
| Tô Lộc Lộc | lulu | Hải Đăng | `hai-dang-drama` | Thiện Minh | MC Dạ Vấn Thiên |
| Xuân Mai | chunmei | Hải Đăng | `hai-dang-drama` | Đức Trí | MC Cố An. Not Thiện Minh for `male`: that timbre is Kiếm Vô Ngân |
| Ngao Chu Diệp | zhuye | Adam bựa | `adam-bua-drama` | Hải Đăng | MC Thẩm Hòe. `nyan-mikuru` handled 300–500 tags per book, breath tags included, with almost no retries |

## Characters

### MCs

| Id | Also called | Canon | Fallback | Who | Books |
|---|---|---|---|---|---|
| Hàn Thần | `ta` in his books | Thiện Minh / `thien-minh-drama` | `adam-bua-drama` (chunmei_v3 cameo) | Sương Nguyệt's husband, easy-going; Ngao Côn's old rival | shuangyue_v1–v5, chunmei_v3 |
| Đồ đệ Khả Khả | `ta`; đồ nhi, đồ đệ, tiểu tử | Thiện Minh | Hải Đăng (meimei_v4) | Khả Khả's disciple | keke_v1–v5, meimei_v4 |
| Sư đệ Ma Hoa | `ta`; sư đệ, dược liệu, đạo lữ, phu quân | Thiện Minh | — | Ma Hoa's unnamed junior disciple and partner | mahua_v1–v5 |
| Lý Vân Chu | `ta`; Vân Chu, Sư tôn, Phong chủ, phụ thân | Thiện Minh / `thien-minh-drama` | Thái Sơn (chunmei_v3–v4, where `thien-minh-drama` is Kiếm Vô Ngân) | Calm, honest sword master; Mị Mị's master, Miêu Miêu's father | meimei_v1–v6, maomao_v3–v5, chunmei_v3–v4 |
| Bếp Trưởng | `ta`; tên tạp dịch, tên phụ bếp, Đầu Bếp, Trù tử, phu quân Miêu Miêu | Hải Đăng / `hai-dang-drama` | Thiện Minh (lulu_v4, chunmei_v4) | Reincarnated backend engineer turned dry kitchen hand; Miêu Miêu's husband | maomao_v1–v5, lulu_v4, chunmei_v4 |
| Hàn Lập | `ta`; Lập sư đệ, Lập nhi, tiểu tử rùa, tên rùa, Hàn thiếu gia | Hải Đăng / `hai-dang-drama` | Thiện Minh (lulu_v5–v6), `thien-minh-drama` (zhuye_v3) | Deadpan, clinical formation master of Hàn Sơn Phong; son of Hàn Thần and Sương Nguyệt; Tiểu Xuân's husband | chunchun_v1–v6, lulu_v5–v6, zhuye_v3 |
| Dạ Vấn Thiên | `ta`; Thiếu chủ, Thánh Tử, Lãnh Chúa, Minh Hà Chi Chủ | Hải Đăng / `hai-dang-drama` | — | Broke, over-dramatic would-be kidnapper of Huyết Liên Giáo; Lộc Lộc's partner | lulu_v1–v6, zhuye_v3 |
| Cố An | `ta`; Cố sư đệ, Mặc Trùng | Hải Đăng / `hai-dang-drama` | — | Calm, dry outer-sect painter of Vô Vân Kiếm Các | chunmei_v1–v5 |
| Thẩm Hòe | `ta`; Lục Văn (fake name), Phá Trủng Tỏa Tượng, tên trộm | Adam bựa / `adam-bua-drama` | — | Wry tomb-raiding locksmith thief; Diệp Nhi's partner | zhuye_v1–v3 |

In his own series the MC's id is `ta`; elsewhere use the name in the Id column.

### Women

| Id | Also called | Canon | Fallback | Who | Books |
|---|---|---|---|---|---|
| Sương Nguyệt | Nguyệt nhi, Tiểu Nguyệt, Sương Ma Nữ, mẫu thân | `shirone-mika` | — | Bratty, possessive ice-cultivator; Hàn Thần's wife, Hàn Lập's mother | shuangyue_v1–v5, chunchun_v1, chunmei_v3 |
| Khả Khả | Tô Khả Khả, cô cô, sư phụ, Tô trưởng lão, Thái Thượng Trưởng lão, Mẹ; `Tô Khả Khả Đại` in a parse | `lynasa` | `pong-kyubi` when Tiểu Xuân speaks in the book (chunchun_v1–v6) | Lazy, hedonistic, boisterous Nguyên Anh elder of Yên Vân Phong; Tiểu Xuân's master, Lộc Lộc's mother | keke_v1–v5, meimei_v4, chunchun_v1–v6, lulu_v1–v5 |
| Ma Hoa | Hoa sư tỷ, Ma đan sư, bánh quẩy nhỏ, Ma di, Ma Hoa di nương | `azu-livyatan` | — | Deadpan Hợp Hoan alchemist; Tiểu Xuân's mother | mahua_v1–v5, maomao_v4, chunchun_v1, lulu_v2 |
| Mị Mị | Cố Niệm, đồ nhi, khôi thủ, Thánh nữ, Mị Mị phu nhân, mẫu thân; `female` in meimei_v1 | `nina-meowmeow` | — | Reincarnated game tester, lazy, lewd, scheming; Miêu Miêu's mother. meimei_v5: three soul shards, same voice; meimei_v6: speaks `tôi`/`anh` | meimei_v1–v6, maomao_v3–v5, chunmei_v4 |
| Miêu Miêu | Lý Miêu Miêu, Tiểu Ma Nữ, bản ma nữ, sư tỷ; `Vệt` in a parse | `shirone-mika` | — | Bratty, haughty Kim Đan prodigy of Vong Vân Phong | maomao_v1–v5, lulu_v1–v2, lulu_v4, chunmei_v4 |
| Tiểu Xuân | Vu Xuân Quyển, Xuân Xuân, nem cuốn, cái ả ồn ào | `lynasa` | — (Khả Khả moves to her fallback instead) | Loud, hot-headed body/spear cultivator; Khả Khả's disciple, Hàn Lập's wife | chunchun_v1–v6, lulu_v5–v6, zhuye_v3 |
| Lộc Lộc | Tô Lộc Lộc, tiểu sư muội, đỉnh lô, ái nữ Yên Vân | `pong-kyubi` | — | Sleepy, seemingly naive "hostage" who is secretly in control | chunchun_v6, lulu_v1–v6, zhuye_v3 |
| Diệp Nhi | Ngao Chu Diệp, long nữ, tiểu nha đầu rồng phượng; `Ngao Chu Diệp` / `Chu Diệp` in the parses | `nyan-mikuru` | — | Loud, lonely, possessive half-dragon half-phoenix Nguyên Anh who breaks whatever she holds | chunchun_v5, zhuye_v1–v3 |
| Xuân Mai | Ẩn Mai Tiên Tử, Băng Mai Tiên Tử, bản sư tỷ; `Vẻ` / `Vị Băng Mai` in a parse | `nika-linh-lan` | — | Cold, haughty, greedy sword prodigy who secretly models for erotic paintings | chunmei_v1–v5 |
| Hoài Thanh | Đệ tử Hoài Thanh | `hoai-thanh-awai` | — | Earnest, naive Bách Thảo Đường disciple | meimei_v3 |
| Mộc Liên Hoa | Mộc trưởng lão, Mộc di; `Mộc` in the parses | `tam-nee` | — | Wry Hợp Hoan elder and schemer who buys and sells everything | shuangyue_v4–v5, mahua_v4–v5, maomao_v4, chunchun_v4, lulu_v2, lulu_v6, chunmei_v3, zhuye_v3 |
| Đoạn Thanh | Đoạn Tình lão tổ; voice of the Uyên Ương Bí Cảnh gate and lanterns | `tam-nee` | — | Weary ghost ancestor, antagonist | shuangyue_v5 |
| Từ Mẫu | Tiểu Từ, Từ di | `tam-nee` | — | Ancient, dry, terrifying matriarch of Thúy Liên Cốc | lulu_v5–v6 |
| Cơ Hồng Loa | Cơ tông chủ, bản tông chủ | `fuyuki-inari` | — | Calm, sharp sect head of Hợp Hoan Tông | shuangyue_v4–v5, maomao_v4, chunchun_v1, lulu_v6 |
| Bạch Thanh Thanh | Liên Hoa Tiên Tử, Bạch trưởng lão | `fuyuki-inari` | — | Prim, easily flustered healer of Thúy Liên Cốc; Ngưu Mãnh's wife | shuangyue_v3, shuangyue_v5, chunchun_v6, lulu_v5–v6 |
| Hỏa Linh | Hỏa Linh phu nhân, Chu Tước, Mẫu thân | `fuyuki-inari` | — | Dry, watchful phoenix; Ngao Côn's wife, Diệp Nhi's mother | shuangyue_v3, shuangyue_v5, meimei_v4, chunchun_v5, zhuye_v1–v2 |
| Kiếm Vô Hà | Các chủ phu nhân, Vô Hà | `fuyuki-inari` | — | Cold co-sect master of Vô Vân Kiếm Các; unison lines with her husband go to Kiếm Vô Ngân | chunmei_v2–v5 |
| Khúc Trinh | Khúc Quả Phụ, ả quả phụ, Tiểu Âm, Khúc thẩm | `ngoc-trinh` | — | Weary relic-selling widow of Quỷ Cốc; will get her own series, keep this voice | lulu_v4, chunmei_v2, chunmei_v5, zhuye_v1 |
| Hồng Tiểu Muội | Hồng Loan, lão nương, bà | `ngoc-trinh` | — | Fierce, motherly ma-đạo cook of Huyết Liên Giáo; Mạc Tà's wife | lulu_v1–v6 |
| Vinh Điệp | Vinh Điệp (danh đào) | `ngoc-trinh` | — | Stern, flamboyant director of the Hí Cảnh Phường theatre | chunchun_v4, chunchun_v6 |
| Hệ thống | Gia thần, the system panel / banners | Thùy Dung (VieNeu) | — | Mị Mị's game system. Its banners are bracketed narration lines (`[MỞ KHÓA NHIỆM VỤ: …]`, `[TÌNH CẢM CỘNG HƯỞNG ↑] ▰▰▱…`); answer each `Hệ thống` (`new: Hệ thống \| female` the first time). From meimei_v5 it also talks in lowercase bracket lines, and in v6 through her old phone; `▰▰▱…` lines are Hệ thống too | meimei_v2–v6 |

`fuyuki-inari`, `ngoc-trinh` and `tam-nee` each cover several characters who have not shared a scene. If two of them speak in the same book, keep the one with more lines on canon and give the other a free voice of the same style, then record it as that character's fallback.

### Men

| Id | Also called | Canon | Fallback | Who | Books |
|---|---|---|---|---|---|
| Liễu lão thư lại | Liễu, họ Liễu, Liễu tiên sinh, Liễu chưởng quỹ | `adam-bua-drama` | Thái Sơn (zhuye_v3, where `adam-bua-drama` is the MC) | Vain, theatrical scribe of Thiên Mặc Đường who writes popular romance books; auctioneer at Huyền Nguyệt Các | keke_v3, keke_v5, meimei_v4, maomao_v1–v2, lulu_v2, lulu_v4, chunmei_v2, chunmei_v5, zhuye_v3 |
| Yến Vô Cực | Khai Quốc Đế Quân, the voice of the stone tablet in Tổ Hoàng Mật Quật; `hoàng đế` in the parse | `adam-bua-drama` (user's choice: he is Thẩm Hòe's ancestor, so he shares the MC's voice on purpose) | — | Gleeful, playful ancestor emperor; author of the Thái Cổ Phủ Linh Chân Kinh | zhuye_v4 |
| Kiếm Vô Ngân | Các chủ, Kiếm Các chủ, Vô Ngân | `thien-minh-drama` | — | Austere, joyless sect master of Vô Vân Kiếm Các | chunmei_v2–v5 |
| Ngao Côn | Ngạo Côn (id in the older books), Chân Long, Thanh Long, Phụ thân, `phụ thân nàng` / `Kiều` in parses | `duc-tri-drama` | — | Vain, boisterous dragon who counts his gold piles and "meditates" (snores); Hỏa Linh's husband, Diệp Nhi's father. Tag him booming, roaring, grumbling, sulking; his "ta đang tọa thiền" excuses are a running joke (defensive, grumbling) | shuangyue_v3, shuangyue_v5, meimei_v4, chunchun_v5, zhuye_v1–v2, zhuye_v5 |
| Vu thúc | Vu thúc | Đức Trí | — | Tiểu Xuân's father, Ma Hoa's husband; huge, gentle, resigned | chunchun_v2–v4, chunchun_v6 |
| Ngưu Mãnh | Ngưu Mãnh | Đức Trí | — | Bạch Thanh Thanh's huge, gentle husband | lulu_v5–v6 |
| Mạc Tà | Mạc lão, lão phu | Thiện Minh | — | Lazy, theatrical Huyết Liên Giáo elder; Hồng Tiểu Muội's husband | lulu_v1–v6 |
| Phụ thân Lộc Lộc | Tảo Địa Đệ Tử, người quét rác, nhạc phụ; `phụ thân` / `Thái Thượng Trưởng` in the parses | Thiện Minh | — | Khả Khả's husband; terse sweeper of Yên Vân Phong, master of traps | lulu_v1, lulu_v3 |
| Đàm Trưởng lão | Đàm | Hải Đăng | — | Grandfatherly Bách Thảo Đường elder, always fooled by Mị Mị | meimei_v1–v3, meimei_v5–v6 |
| Bách Vị Tiên Nhân | gương mặt đá, vị tiên nhân | Hải Đăng | — | Deceased trial creator, voice of Bách Vị Bia | mahua_v3 |
| Trận Linh | trận linh Cửu Yên Luyện Cảnh, lão giữ cửa | Thùy Dung (VieNeu) | — | Dry, weary trial spirit who keeps Khả Khả's sect memories | keke_v5 |

Đức Trí and Thiện Minh each cover several men. When one of them is the book's `male` role or narrator, the listed man keeps it and the other men move to another `male` voice. `duc-tri-drama` is the Drama-3 clone of Đức Trí, so it counts as the same timbre: Vu thúc and Ngưu Mãnh (VieNeu Đức Trí) should not share a scene with Ngao Côn; if they do, move them to Thái Sơn.
