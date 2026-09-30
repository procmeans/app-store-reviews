# Multilingual gameplay research

Reviews are only one layer. Gameplay, design intent, level structure, who made
it first and why it worked are discussed in local-language guides, videos,
press and developer posts. Cover these languages by default:

**en, tr, vi, ja, ko, fr, de, es** (+ zh when relevant).

Turkish and Vietnamese matter disproportionately: Istanbul/Ankara is the hub of
hyper/hybrid-casual studios (Rollic, Good Job Games, Grand Games, Loom, Ace,
Bigger, Magic Games, Paxie, Cypher...), and Vietnam is a huge source of fast
clones and hybrid-casual publishers (iKame, ABI, Amanotes, Onesoft, Falcon,
Sonat, Vnstart, Zego...). Their developers, press and LinkedIn/Medium posts
often explain mechanics, test results and failed prototypes that English
sources never cover.

## Step A — get the local words from the stores, not from your head

```bash
python3 scripts/localized_listings.py --ios-id <id> --gp-id <pkg> --out data/<slug>/<app>_listings
```

For each language, note: the local name of the mechanic (e.g. ja リング回転,
ko 링 회전, tr halka döndürme, vi xoay vòng), the verbs used (rotate / align /
unlock), advertised mechanics and boosters, and positioning (relax, brain
training, ASMR). A listing that is the same English text in every language
means the game was not localized for that market — itself a signal.

Feed the local terms into a second `market_scan.py --keywords` pass to catch
local clones that English search misses.

## Step B — web search per language

Combine `<local mechanic name>` or `<game name>` with these words. Run at
least 2 searches per language; open the best 1–3 results.

Industry analysis sites per language are in `industry-sites.md` (separate, mandatory step). The sites below are for gameplay/guides/player reviews.

| Lang | Gameplay / guide | Review / impressions | Dev / industry | Gameplay & community sites |
|---|---|---|---|---|
| en | how to play, walkthrough, level | review, gameplay | deconstruction, soft launch, prototype, CPI test | deconstructoroffun.com, mobilegamer.biz, pocketgamer.biz, reddit r/iosgaming r/AndroidGaming, YouTube |
| tr | nasıl oynanır, bölüm, çözüm | inceleme, oyun yorumu | hyper casual, hibrit casual, oyun geliştirme, prototip, test, yayıncı | webrazzi.com, egirisim.com, oyunhaber, LinkedIn/Medium posts by Turkish studios |
| vi | cách chơi, hướng dẫn, màn, qua màn | đánh giá, review game | game hyper casual, làm game, phát triển game, test CPI, publisher | genk.vn, gamek.vn, vnexpress.net/so-hoa, viblo.asia, Facebook groups "Vietnam Game Developers" |
| ja | 遊び方, 攻略, ステージ, 解き方 | レビュー, 評価, 感想 | ハイパーカジュアル, 開発, パブリッシャー | appmedia.jp, app-liv.jp, gamewith.jp, 4gamer.net, note.com, X/Twitter |
| ko | 공략, 플레이 방법, 스테이지 | 리뷰, 후기, 평가 | 하이퍼캐주얼, 개발, 퍼블리셔 | inven.co.kr, gamemeca.com, ruliweb.com, 블로그 (naver/tistory) |
| fr | comment jouer, niveau, solution | avis, test | hyper-casual, développement, éditeur | jeuxvideo.com, iphon.fr, frandroid.com, numerama.com |
| de | Anleitung, Level, Lösung | Test, Erfahrungen, Bewertung | Hyper-Casual, Entwicklung, Publisher | curved.de, giga.de, mobilegeeks.de, computerbild.de |
| es | cómo jugar, nivel, solución | reseña, opinión | hipercasual, desarrollo, publisher | 3djuegos.com, xataka.com, andro4all.com, applesfera.com |
| zh | 玩法, 攻略, 关卡 | 评测, 测评 | 超休闲, 混合休闲, 立项, 测试, 爆款拆解 | gamelook.com.cn, youxiputao.com, 白鲸出海, DataEye, 知乎, B站, 抖音 |

YouTube: search `<game name> gameplay` plus the local guide word
(`攻略`, `공략`, `bölüm`, `cách chơi`, `solution`, `Lösung`, `nivel`). Titles,
level numbers and view counts show which levels/mechanics players get stuck on
and how big the game is in that market.

## What to extract per language (write it down as you go)

- Mechanic as described locally, and any mechanic or mode not in the English listing.
- Where players get stuck (level numbers from guides/videos).
- Market-specific complaints or praise not seen in English sources.
- Local studios making the same mechanic, and any dev/postmortem/test-result posts.
- Quote original text + a Chinese translation; tag as [第三方] with URL.

Report this as a "多语言玩法与市场差异" table in the final report: one row per
language, columns = 当地叫法 / 本地定位 / 独有发现 / 来源.
