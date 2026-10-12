# x68k_vgm2mml

VGMを検査可能な中間表現へ変換し、その中間表現を経由してMDX用MMLを生成するツールです。現状はYM2151、YM2608のFM、MSM6258、SCC、PSGの一部の音源に対応しています。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報を、X68000で扱えるMMLとして表現することです。

出力の時間精度は `--normalization-ms`（既定8ms）で調整できます。値を小さくすると細かな発音イベントを保持し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

Python 3.10以降を使用します。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

ターゲットの既定値はMDX用MMLで、`OUTPUT/input.mdx.mml` を生成します。`--outdir` を省略した場合は入力ファイルと同じディレクトリへ出力します。fixtureの検証には入力と異なる出力先を指定してください。

VGMの実際のコマンドから使用音源を判定し、OPM／PCM、OPNA FM／SSG、または対応するPSG／SCC入力の経路を選択します。未対応の音源・組み合わせ・ストリームは診断情報として報告します。

### 入力と出力

| 入力 | 主な出力・変換経路 |
|------|------|
| OPM（YM2151） | OPMの状態・SegmentからMDX用MMLを生成 |
| OPNA（YM2608）のFM | Native SegmentからOPM（4MHz）へ投影し、既存OPM経路でMDX用MMLを生成 |
| OPNAのSSGトーン | 既存PSGのFM方式でOPMへ投影。曲全体でFMを優先し、残りのOPMチャンネルへ割り当て |
| OPNAのADPCM-B（Delta-T） | 元のIRを保持し、MSM6258へ再圧縮して既存Pトラック／PDX経路へ接続（`best-effort`） |
| PSG／SCC | OPM向け音色・演奏情報へ投影してMDX用MMLを生成 |
| 対応するMSM6258 PCM（OPM併用を含む） | PCM IRとMDX用MMLを生成し、外部helperでMDX／PDXを生成 |

OPMのみのMML生成にRustコンパイラは不要です。PCMを含む通常変換では外部helperのビルドが必要です。

OPNA FM→OPMには [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) のOPN→OPM方式を採用しています。音色・operator・キー・左右出力を対応付け、元の11bit FNUM/BLOCKから既存のKC/KF処理で4MHz向けの音程を生成します。外部のvgm-convコマンド実行は不要です。参照実装のISC表示は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#vgm-conv) に保持しています。

OPNAのFM・SSGをMDXへ投影し、ADPCM-Bは別のPCM経路へ渡します。SSGには既存PSGと同じFM音色・音量対応・発音推定を使用します。曲全体で使用チャンネルを調べ、FMを優先してOPMの8チャンネルへ割り当てます。残りをSSGの番号順に使用し、割り当て可能数を超えたSSGチャンネルは省略し、その旨を診断情報へ記録します。

割り当て結果は `<stem>.opna_channel_allocation.csv` および `.json` に保存します。FM 6＋SSG 3を使用する場合、SSGの3番目は省略されます。

SSGのノイズ・ハードウェアエンベロープには既存PSG投影と同じ未対応診断を適用します。リズムは出力対象外です。CH3特殊モード・CSM・未知のレジスタ効果・DACストリームは拒否し、FMのSSG-EGやLFOなどの近似・省略は `<stem>.opna-opm.json` に記録します。

`--dump-passes` では元のOPNA Raw／FM State／Segment、SSG Segment、`projected_opm/` のOPM VGM・対応CSV・既存OPMパスを保存します。詳細は[docs/opna_ssg.md](docs/opna_ssg.md)を参照してください。

OPNAのADPCM-B（Delta-T）は、元のメモリ・制御・再生区間を `<stem>.opna_adpcm.*` に保存します。

対応する独立再生区間は、デコード・レート変換・再圧縮したMSM6258向けPCM IRを `<stem>.msm6258_ir.*` として出力し、既存のPトラック・外部helperによるMDX／PDX生成へ渡します。

FMとPCMは同じMDXクロックを使用します。

近似を伴うため、既定の `strict` では停止し、`--pcm-policy best-effort` を指定した場合のみ生成します。未対応のデコーダ継続などはこの設定でも拒否します。

変換対応表は `<stem>.opna_pcm_bridge.json`、損失情報は `<stem>.pcm.assessment.json` に記録します。

詳細は[docs/opna_adpcm.md](docs/opna_adpcm.md)を参照してください。

## VGMの曲全体ループ

VGMヘッダーに指定されたループは、既定でMDX用MMLへ引き継ぎます。

読み取り段階で音源状態を保ったままループ部分をもう1周展開し、増えたSegmentを既存の構造化処理へ渡します。MMLでは最初の1周を通過した後、2周目の入口に `L` を配置して繰り返します。境界で新たなKey-Onや状態リセットは追加しません。

有限1周で終了させたい場合は `--no-song-loop` を指定してください。これは、MML内の有限反復圧縮を無効にする `--no-loops` とは別の設定です。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input --no-vgm

python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/finite \
  --no-vgm \
  --no-song-loop
```

`--dump-passes` では、元の命令位置・時刻、展開後の時刻、周回番号をCSVに記録します。

発音がループ境界をまたぐFM部分は制御命令として保持します。PCMは独立して再生できるサンプルを対象とし、境界をまたぐデコーダ継続は診断情報として報告したうえで拒否します。

legacy表記とPSG/SCCのheld-register互換経路では、現在は `--no-song-loop` が必要です。

詳細は[docs/vgm_loop.md](docs/vgm_loop.md)を参照してください。

## X68000と異なるOPMクロックの入力

単一のYM2151であれば、3,579,580Hzなど4MHz以外の入力も変換できます。

入力クロックはVGMヘッダーから読み取り、**Segment → Target (MML)** の段階でKC/KFを4MHz向けに補正します。

`structured`／`legacy`／`registers`、PCM併用にも共通で適用し、追加オプションは不要です。元のState・Segmentは変更しません。

補正は公称の基本音程を1/64半音単位へ丸める処理です。音色のDT1、エンベロープ、LFO、ノイズ速度までは補正しません。これらを補正しないこと自体では変換を拒否しません。

未書き込みKC/KFの初期値は出力側で0と仮定して記録します。

KC/KFだけでは指定できない範囲の音程は、既定の `--opm-pitch-policy clamp` により最も近い端の音程へ丸めます。

これはKC/KFの指定範囲による制約であり、音色倍率変更などを含むハードウェア全体としての再現可能性を意味するものではありません。

音程差と件数はTXT／CSVへ記録します。範囲外を拒否したい場合は `--opm-pitch-policy error` を指定してください。

TXTの `OPM clock and pitch projection` では、入力／出力クロック、丸め誤差、初期値仮定を確認できます。

`--dump-passes` では、

- `<stem>.mdx.pitch.csv`
- `<stem>.mdx.controls.csv`

を出力し、元のKC/KFと補正値、および元命令と出力命令を記録します。

詳細は[docs/opm_clock_projection.md](docs/opm_clock_projection.md)を参照してください。
## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを生成する際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表現可能な時間単位へ変換する必要があります。

本プロジェクトでは、次の段階を区別します。

```text
VGM commands → Raw → State → Segment → Target (MML / PCM projection)
```

- **Raw／State／Segment**: 元VGMの事実と解析結果を検査可能な形で保持します。
- **Target**: MDXの音価・クロック・命令の制約に合わせて表現します。
- **診断**: 元データから何を省略・近似したか、何を検証できていないかを記録します。

極端に短い発音や細かな制御イベントをすべて厳密にMMLへ写すと、曲全体のタイマークロックが必要以上に細かくなる場合があります。

そこでターゲット出力に限り、短い発音を省略し、許容誤差内でタイマークロックを選択します。

**`--normalization-ms 8` が現在の既定値です。**

正規化前のKey-OnからKey-Offまでの発音全体が閾値以下であれば、出力から省略できます。同じ値を出力時刻の最大移動量にも使用します。

発音中の細かな制御区間を短い音符と見なして削除する処理ではありません。

短い休符が統合される場合でも、Key-Off／Onの順序は保持し、元のSegmentやPCM IRは変更しません。

```bash
python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/input \
  --normalization-ms 16
```

値を大きくしても、残す発音区間や時刻制約によってクロックが必ず長くなるとは限りません。

`--no-normalize-lengths` により、この補正を無効化できます。

MML生成に成功したことは、元VGMとの音声一致を意味しません。

変換結果の Summary report（`.report.txt`）や診断JSON／CSVを確認し、変換上の損失・時刻誤差・未検証事項を確認してください。

レポート生成箇所や対象項目は実行経路によって異なります。

## フォルダ指定による一括変換とMDX／PDX生成

`scripts/export_mdx.py` は単一ファイル、またはフォルダ以下の `.vgm`／`.vgz` を処理します。

```bash
# PSG/SCC入力
python scripts/export_mdx.py tests/fixtures/public/psg \
  --outdir outputs/listen/psg

# ネイティブOPM入力
python scripts/export_mdx.py tests/fixtures/public/opm/from_mdx \
  --outdir outputs/listen/opm
```

入力と出力は別フォルダにしてください。

結果は `results.csv` で確認できます。成功したファイルだけでなく、失敗理由や診断結果も記録します。

公開用成果物と診断用成果物は分離して保存します。

FMのみの入力では、MMLからMDXへのコンパイルに既定でMXC（MXC.X）を使用します。X68000用実行ファイルの実行には run68x の run68 が必要です。

`--compiler mmlx` で別のコンパイラを明示的に選択できます。

生成したMDXからのOPM VGM出力には soundlog を利用します。

WSLで外部ツールをまとめて準備するには、次を実行します。

```bash
bash scripts/setup_tools.sh
```

MXC v1.01、固定リビジョンのrun68x、および Cargo.lock に固定された mmlx／soundlog を利用するRust helperを導入します。

MXC／run68はGit管理対象外の `.tools/`、helperは `scripts/mdx_fixture_generator/target/` に配置するため、`outputs/` を削除しても残ります。

システムへのインストールやsudo実行は行いません。

調査・リファレンス比較用の **mdxinfo・pdxinfo・mdxdump・mdx2mml** も用意する場合は、次を実行します。

```bash
bash scripts/setup_tools.sh --with-mdxtools
```

従来 `research` 配下に置いていた実行ツールはこちらへ集約します。過去の調査結果そのものを再生成するコマンドではありません。

Python 3.10以降、Rust/Cargo、Cコンパイラ、CMake、make、git、curl、および初回のMXC展開用 lha／lhasa が必要です。

準備方法と固定バージョンは[docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md)を参照してください。

同じスクリプトを再実行でき、導入したバイナリのハッシュとリビジョンは `.tools/setup_manifest.json` に記録します。

MXC／run68のパスは `--mxc`／`--run68` で指定できます。

外部ツールはリポジトリには同梱しません。

```bash
python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/input \
  --mxc /path/to/MXC.X \
  --run68 /path/to/run68
```

出力したMDXがコンパイルできることと、MXDRV／MMDSP上で正常に表示・演奏できることは区別してください。

MDX→VGMを生成できた場合も、それだけでは元VGMとの音声一致を証明しません。

## PCMを含むVGMからMML・MDX・PDXを生成する

対応するMSM6258入力には、直接レジスタ書き込み、および対応する非圧縮Data Bank／有限DAC Streamがあります。PCMのみの入力も対象です。

OPNAのADPCM-Bも、対応する独立再生区間からMSM6258へ変換して接続できます。

再圧縮による近似を許容する場合は `--pcm-policy best-effort` を指定してください。

```bash
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes

# 既知の投影損失を診断付きで許容する場合
python vgm2mml.py input.vgm \
  --outdir outputs/input-best \
  --pcm-policy best-effort \
  --dump-passes

# OPNAのFM・ADPCM-Bから再生確認用MDX／PDXを出力
python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/opna \
  --no-vgm \
  --pcm-policy best-effort
```

PCMを含む経路では、MMLに加えてMDX／PDXも生成します。

可読MMLにはPCM参照を記述しますが、PCM部分のMDX生成は型付き命令列から行い、MMLテキストそのものには依存しません。

- `strict`（既定）: 既知の意味損失を伴う投影は停止
- `best-effort`: 定義済み近似の範囲内で生成し、失われる情報を診断情報として記録

未対応入力を無条件に変換する設定ではありません。

PCMの符号化バイト列・サンプル同一性と、供給タイミング・STOP／PLAY・panなどの再生情報は区別して扱います。

元のPCM IRを維持し、PDXへの投影で失われる情報を記録します。

MDX／PDXはセットでプレイヤーへ渡してください。

**PCMを含むMDXからのVGM再生成は、現時点では利用できません。**

MDX／PDXの生成成功と、独立した再生検証は別の結果です。

詳細は[docs/pcm_pdx.md](docs/pcm_pdx.md)を参照してください。

PCMを含む一括出力では、VGM再生成を要求しない `--no-vgm` を指定できます。

```bash
python scripts/export_mdx.py tests/fixtures/public/opm_msm6258 \
  --outdir outputs/listen/opm_msm6258 \
  --no-vgm \
  --pcm-policy best-effort
```

## 互換性と主なオプション

MGSDRV形式への既存変換を使用する場合は、ターゲットを明示します。

```bash
python vgm2mml.py input.vgm --target mgs --outdir OUTPUT
```

MDX側の主なオプションは次のとおりです。

| オプション | 内容 |
|------------|------|
| `--notation structured` | 音符・制御軌跡・有限反復による表記（既定） |
| `--notation legacy` / `registers` | 互換表記／レジスタ制御表記 |
| `--normalize-lengths` / `--no-normalize-lengths` | structured MDXの長さ補正の有効／無効 |
| `--normalization-ms MS` | 正規化前の短い発音の省略閾値と出力時刻の最大移動量 |
| `--no-loops` | 有限反復の生成を無効化 |
| `--psg-model fm\|additive` | PSGからOPMへの音色投影モデル |
| `--psg-gain` / `--scc-gain` | PSG／SCC投影時の音量調整 |
| `--pcm-policy strict\|best-effort` | PCM投影で既知損失を許容するか |
| `--dump-passes` | 中間CSV・診断ファイルを保存 |

ここでいう **有限反復** は、VGMヘッダーに記録された **曲ループ** とは別です。

VGMヘッダーの曲ループについては、「VGMの曲全体ループ」で説明したとおり出力できます。

有限反復は、構造化されたMML表記において同一パターンを圧縮するための機能です。

詳細な制約とその他のオプションは次を参照してください。

```bash
python vgm2mml.py --help
```
## 統計情報レポートの見方

`export_mdx.py` は曲ごとに `tracks/<stem>/<stem>.txt` を生成します。

演奏用のMML・MDX・必要なPDXも同じ場所に配置し、中間結果やコンパイラ入力は `_diagnostics/` に分離します。

全曲の成否は `results.csv` で確認できます。

まず `Export` と `Compiler` を確認してください。

`success` はファイル生成の成功を示しますが、元音源との音声一致やMMDSPでの表示・停止を保証するものではありません。

`Source` は元データ、`Compiled target` は生成MDXの集計です。

レジスタへのKey-On／Off要求数、実際のオペレータ状態変化、MDXの音符数は、それぞれ異なる指標であることに注意してください。

`Output normalization` は出力時の省略・近似、およびクロック選択を示します。

`source samples` はVGMの44,100Hz時間単位であり、PCMの符号化バイト数ではありません。

- 1 sample ≒ 0.02268ms
- 352 samples ≒ 7.98ms

| 項目 | 読み方 |
|------|------|
| Note normalization | `applied` の場合、長さ補正を採用しています。続く説明に、残る発音や休符の扱いを記載します。 |
| Normalization parameter | `--normalization-ms` の設定値です。発音全体に対する省略閾値と、出力境界の最大移動量を兼ねます。 |
| Short-note omission | `adopted=True` は省略処理を採用したことを示します。実際の省略数は `FM gates`／`PCM playbacks`、省略した発音時間は `FM duration` です。 |
| Coalesced positive control intervals | 近接する制御境界を同一出力時刻へまとめた区間数です。音符を削除した数ではありません。 |
| Coalesced short rests | 出力で正の長さを失った短い休符の数と元の合計時間です。Key-Off／Onの順序は保持します。 |
| Boundary allocation | `bounded_ordered` は、許容移動量の範囲で境界を調整したことを示します。 |
| Selected MDX clock | 採用した1tickの時間とテンポ値です。MMLの `@t` がMDXのTimer B値を指定します。 |
| Rejected MDX clock candidates | 他候補を採用できなかった理由です。候補却下自体は変換失敗ではありません。 |

例えば

```text
Selected MDX clock: 16128 us/tick;
tempo byte 193;
MML @t193
```

は、約16.128ms周期の設定を意味します。

設定値8msに対し、最大移動350 samplesは約7.94msで許容範囲内ですが、候補誤差362 samplesは約8.21msとなるため採用できません。

`example kinds` は例示であり、全区間を種類別集計したものではありません。

`PCM assessment` は、

- PCM投影の成否
- PDXに格納された符号化データ
- 周波数対応
- 再生境界の時刻誤差

を個別に報告します。

`not available / no PCM projection` は、その結果にPCM投影評価が存在しないことを意味し、単独ではエラーではありません。

`Known losses` は既知の損失、`Unverified`／`unmeasured` は未確認事項を示します。

`Diagnostics` には実行時の失敗理由や取得できなかった統計を記録します。

例えば `Missing --mxc tool` が表示された場合は、コンパイラ導入後に再実行し、最新の `results.csv` とTXTを確認してください。

古い失敗レポートと、現在の成功結果は区別して判断してください。

## 中間結果と検証

OPNA（YM2608）はReaderとFM State／Segment解析に対応し、通常変換ではOPMへ投影してMDX用MMLを生成します。

SSGはRawとは別のSegmentからPSGのFM方式でOPMへ投影します。

リズムはRawとして保存し診断情報へ記録します。

ADPCM-Bは独立したメモリ／再生IRからMSM6258へ変換します。

```bash
python py/vgm_reader.py input.vgm outputs/opna-analysis
```

全チャンネルを含むRaw・State・Segment CSVと、未解釈writeのCSVを生成します。

API・フィールド・検証範囲は[docs/opna_segments.md](docs/opna_segments.md)を参照してください。

```bash
python vgm2mml.py input.vgm --outdir OUTPUT --dump-passes

python -m unittest discover -s tests/scripts -v
```

OPMのRaw／State／Segment、制御・構造・タイミング情報、PCM転送・投影・評価情報を保存し、元データと出力結果の対応を確認できます。

fixtureは既存の

- `tests/fixtures/public`
- `tests/fixtures/local_only`

の構造を維持します。

OPMの往復検証は、外部helperをビルドしたうえで実行します。

```bash
python scripts/verify_opm_mdx_roundtrip.py \
  tests/fixtures/public/opm \
  --outdir outputs/opm/roundtrip
```

検証経路は次のとおりです。

```text
VGM
 → Segment
 → MML
 → MDX
 → VGM
 → Segment
```

往復検証結果と、実機／エミュレータでの聴感・表示確認は区別してください。

詳細は以下を参照してください。

- [docs/opm_note_lengths.md](docs/opm_note_lengths.md)
- [docs/psg_scc_opm.md](docs/psg_scc_opm.md)
- [docs/pcm_roundtrip_validation.md](docs/pcm_roundtrip_validation.md)

## 構成

- `vgm2mml.py` : 通常変換の入口
- `py/opm_conversion.py` : OPM入力からMDXへの変換手順
- `py/psg_scc_conversion.py` : PSG／SCC入力からOPM MDXへの変換手順
- `py/` : 音源解析、中間表現、ターゲット生成
- `scripts/` : 一括出力、診断、往復検証、fixture生成、比較用ツール
- [docs/project_knowledge.md](docs/project_knowledge.md): 変換の原則と制約

## ライセンス

Copyright (c) 2026 emef2247.

Licensed under the MIT License.

テスト用VGM生成・外部検証に使用するMUCOMVGMもMIT Licenseで、著作権表示は以下です。

```text
Copyright (c) 2026 WING
```

使用版のライセンス全文と確認元は

`THIRD_PARTY_NOTICES.md#mucomvgm-005`

に保持しています。

MUCOMVGM本体はリポジトリへ同梱せず、再配布する場合は同ライセンスの著作権表示および許諾文を含めてください。

## 謝辞

本プロジェクトのMDX／VGM出力および往復検証では、以下のツールを利用しています。

開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 | 確認した利用条件 |
|------|------|------|
| MUCOMVGM v0.0.5（WING） | テスト用MUC→VGM生成、およびOPNA FM制御状態の往復検証 | MIT |
| MXC v1.01（MFS soft, milk） | MML→MDXコンパイル | フリーウェア・配布自由 |
| run68x | MXCなどHuman68kプログラムの実行 | GPL v2以降 |
| mmlx 0.2.0 | 明示選択時のMML→MDXコンパイル、およびPCM経路のFM部分 | MIT |
| soundlog 0.15.0 | FMのMDX→VGM、PDX構築・PCM参照検査 | MIT |
| vgm-conv | PSG→OPMの音色・音量対応、およびOPNA FM→OPMのレジスタ対応方式 | ISC |
| mdxtools（任意導入） | MDX／PDXの独立検査と逆コンパイル | GPL v3 |

OPNA FM→OPMおよび PSG／SSG→OPM は、vgm-convの対応方式を参照してPython側に実装しています。

通常変換時に外部のvgm-convコマンドを実行するわけではなく、そのライブラリも不要です。

参照した対応方式のISC著作権表示・許諾文は `THIRD_PARTY_NOTICES.md` に保持しています。

各ツールの使用版・確認元・著作権表示・配布時の扱いは `THIRD_PARTY_NOTICES.md` に記録しています。

vgm-convのISC全文、およびMUCOMVGM／mmlx／soundlogのMIT全文も保持しています。

本プロジェクトのMITライセンス表記とあわせて、これらの表示も配布物へ含めてください。

セットアップで取得する

- MXC
- run68x
- mdxtools

はローカルの外部ツールであり、リポジトリや試聴用出力へは同梱しません。

これらを別途再配布する場合は、それぞれのライセンス条件に従ってください。

Rust helperのバイナリを配布する場合は、直接利用している mmlx／soundlog に加え、推移的依存ライブラリのライセンス表示も必要です。

外部コンパイラや再生ツールは用途に応じて別途用意してください。

本プロジェクトが主に行うのはMMLの生成です。

ただし、生成したMMLの確からしさを検証するため、MML以降のコンパイラや再生ツールを利用するスクリプトを同梱しています。



