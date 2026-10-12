# x68k_vgm2mml

VGMから、検査可能な中間表現を経由してMDX用MMLを生成するツールです。現状はym2151,ym2608のFM,msm6258,scc,psgの一部の音源に対応しています。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報をx68000で扱えるMMLとして取り出すことです。

出力の時間精度は **`--normalization-ms`（既定8ms）** で調整できます。値を小さくすると細かい演奏を残し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

Python 3.10以降を使用します。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

既定のターゲットはMDX用MMLで、`OUTPUT/input.mdx.mml`を生成します。`--outdir`を省略した場合は入力ファイルと同じディレクトリへ出力します。fixtureの検証には入力と異なる出力先を指定してください。

VGMの実際のコマンドから使用音源を判定し、OPM／PCM、OPNA FM／SSG、または対応するPSG／SCC入力の経路を選択します。未対応の音源・組み合わせ・ストリームは診断します。

### 入力と出力

| 入力 | 主な出力・変換経路 |
|---|---|
| OPM（YM2151） | OPMの状態・SegmentからMDX用MMLを生成 |
| OPNA（YM2608）のFM | Native SegmentからOPM（4MHz）へ投影し、既存OPM経路でMDX用MMLを生成 |
| OPNAのSSGトーン | 既存PSGのFM方式でOPMへ投影。曲全体でFMを優先し、残りのOPMチャンネルへ割り当て |
| OPNAのADPCM-B（Delta-T） | 元のIRを保持し、MSM6258へ再圧縮して既存Pトラック／PDX経路へ接続（`best-effort`） |
| PSG／SCC | OPM向け音色・演奏に投影してMDX用MMLを生成 |
| 対応するMSM6258 PCM（OPM併用を含む） | PCM IRとMDX用MMLを生成し、外部helperでMDX／PDXを生成 |

OPMのみのMML生成にRustコンパイラは不要です。PCMを含む通常変換では外部helperのビルドが必要です。

OPNA FM→OPMには[vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)のOPN→OPM方式を採用しています。音色・operator・キー・左右出力を対応付け、元の11bit FNUM/BLOCKから既存のKC/KF処理で4MHz向けの音程を生成します。外部vgm-convの実行は不要です。参照実装のISC表示は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#vgm-conv)に保持しています。

OPNAのFM・SSGをMDXへ投影し、ADPCM-Bは別のPCM経路へ渡します。SSGには既存PSGと同じFM音色・音量対応・発音推定を使用します。曲全体で使用チャンネルを調べ、FMを優先してOPMの8チャンネルへ割り当てます。残りをSSGの番号順に使用し、入りきらないSSGは省略して診断します。割り当て結果は `<stem>.opna_channel_allocation.csv`／`.json` に保存します。FM 6＋SSG 3を使う場合、SSG 3番目が省略されます。

SSGのノイズ・ハードウェアエンベロープには、既存PSG投影と同じ未対応診断を適用します。リズムは出力対象外です。CH3特殊モード・CSM・未知のレジスタ効果・DACストリームは拒否し、FMのSSG-EGやLFOなどの近似・省略は `<stem>.opna-opm.json` に記録します。`--dump-passes`では元のOPNA Raw／FM State／Segment、SSG Segment、`projected_opm/` のOPM VGM・対応CSV・既存OPMパスを保存します。[SSGの変換と割り当て](docs/opna_ssg.md)を参照してください。

OPNAのADPCM-B（Delta-T）は、元のメモリ・制御・再生区間を `<stem>.opna_adpcm.*` に保存します。対応する独立再生区間は、デコード・レート変換・再圧縮したMSM6258向けPCM IRを `<stem>.msm6258_ir.*` として出力し、既存のPトラック・外部helperによるMDX／PDX生成へ渡します。FMとPCMは同じMDXクロックを使用します。近似を伴うため、既定の`strict`では停止し、`--pcm-policy best-effort`で生成します。未対応のデコーダ継続などはこの設定でも拒否します。変換対応表は `<stem>.opna_pcm_bridge.json`、損失は `<stem>.pcm.assessment.json` に記録します。[PCM IRの範囲](docs/opna_adpcm.md)を参照してください。

### VGMの曲全体ループ

VGMヘッダーに指定されたループは、既定でMDX用MMLへ引き継ぎます。読み取り段階で音源状態を保ったままループ部分をもう1周展開し、増えたSegmentを既存の構造化処理へ渡します。MMLでは最初の1周を通過した後、2周目の入口に L を置いて繰り返します。境界で新たなKey-Onや状態リセットは追加しません。

有限1周で終了させたい場合は --no-song-loop を指定してください。これは、MML内の有限反復圧縮を無効にする --no-loops とは別の設定です。

    python scripts/export_mdx.py input.vgm --outdir outputs/listen/input --no-vgm
    python scripts/export_mdx.py input.vgm --outdir outputs/listen/finite --no-vgm --no-song-loop

--dump-passesでは、元の命令位置・時刻、展開後の時刻、周回番号をCSVで追跡できます。発音がループ境界をまたぐFM部分は制御命令として保持します。PCMは独立して再生できるサンプルを対象とし、境界をまたぐデコーダ継続は診断して拒否します。legacy表記とPSG/SCCのheld-register互換経路では、現在は --no-song-loop が必要です。詳細は[ループ処理](docs/vgm_loop.md)を参照してください。

### X68000と異なるOPMクロックの入力

単一のYM2151であれば、3,579,580Hzなど4MHz以外の入力も変換できます。入力クロックはVGMヘッダーから読み、**Segment → Target (MML)** でKC/KFを4MHz向けに補正します。`structured`／`legacy`／`registers`、PCM併用にも共通で適用し、追加オプションは不要です。元のState・Segmentは変更しません。

補正は公称の基本音程を1/64半音単位へ丸める処理です。音色のDT1、エンベロープ、LFO、ノイズの速度までは補正しません。これらの速度を補正しないこと自体では変換を拒否しません。未書き込みKC/KFの初期値は出力側で0と仮定して記録します。

KC/KFだけでは指定できない範囲の音程は、既定の`--opm-pitch-policy clamp`で最も近い端の音程を選びます。Segmentへの独自の許容枠ではなく、KC/KFの指定範囲による制限です。音色の倍率変更などを含めたHW全体での再現不可能を意味しません。音程差と件数をTXT／CSVに記録します。範囲外を拒否したい場合は`--opm-pitch-policy error`を指定してください。

TXTの`OPM clock and pitch projection`で入力／出力クロック、丸め誤差、初期値の仮定を確認できます。`--dump-passes`では`<stem>.mdx.pitch.csv`に元のKC/KFと補正値、`<stem>.mdx.controls.csv`に元の命令と出力命令を記録します。詳細は[OPMクロック補正](docs/opm_clock_projection.md)を参照してください。

## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを作る際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表せる時間単位に変換する必要があります。

本プロジェクトでは、次の段階を区別します。

```text
VGM commands → Raw → State → Segment → Target (MML / PCM projection)
```

- **Raw／State／Segment**：元VGMの事実と解析結果を検査できる形で保持します。
- **Target**：MDXの音価・クロック・命令の制約に合わせて表現します。
- **診断**：元データから何を省略・近似したか、何を検証できていないかを記録します。

極端に短い発音や細かい制御イベントをすべて厳密にMMLへ写すと、曲全体のタイマークロックが必要以上に細かくなる場合があります。そこで、ターゲット出力に限って短い発音を省略し、許容誤差内でタイマークロックを選択します。

**`--normalization-ms 8` が現在の既定値です。** 正規化前のKey-OnからKey-Offまでの発音全体が閾値以下なら、出力から省略できます。同じ値を出力時刻の最大移動量にも使用します。発音中の細かい制御区間を短い音符と見なして削除する処理ではありません。短い休符がまとまる場合もKey-Off／Onの順序は保持し、元のSegmentやPCM IRは変更しません。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input --normalization-ms 16
```

値を大きくしても、残す発音区間や時刻の制約によりクロックが必ず長くなるとは限りません。`--no-normalize-lengths`でこの補正を無効化できます。

MMLの生成に成功したことは、元VGMと音が一致することを意味しません。変換のSummary report（`.report.txt`）や診断JSON／CSVで、変換上の損失・時刻誤差・未検証事項を確認してください。レポートの生成箇所や対象項目は実行経路により異なります。

## フォルダ指定による一括変換とMDX／PDX生成

`scripts/export_mdx.py`は単一ファイル、またはフォルダ以下の`.vgm`／`.vgz`を処理します。

```bash
# PSG/SCC入力
python scripts/export_mdx.py tests/fixtures/public/psg \
  --outdir outputs/listen/psg

# ネイティブOPM入力
python scripts/export_mdx.py tests/fixtures/public/opm/from_mdx \
  --outdir outputs/listen/opm
```

入力と出力は別フォルダにしてください。結果は`results.csv`で確認できます。成功したファイルだけでなく、失敗理由や診断結果も残します。公開用成果物と診断用成果物は分離して保存します。

FMのみの入力では、MMLからMDXへのコンパイルに既定でMXC（MXC.X）を使用します。X68000用実行ファイルの実行には`run68x`の`run68`が必要です。`--compiler mmlx`で別のコンパイラを明示選択できます。生成したMDXからのOPM VGM出力はsoundlogを利用します。

WSLで外部ツールをまとめて準備するには、次を実行します。

```bash
bash scripts/setup_tools.sh
```

MXC v1.01、固定リビジョンのrun68x、Cargo.lockに固定されたmmlx／soundlogを利用するRust helperを導入します。MXC／run68はGit管理対象外の`.tools/`、helperは`scripts/mdx_fixture_generator/target/`に置くため、`outputs/`を削除しても残ります。システムへのインストールやsudo実行は行いません。

調査・リファレンス比較用の **mdxinfo・pdxinfo・mdxdump・mdx2mml** も用意する場合は、次を実行します。従来`research`配下に置いていた実行ツールはこちらへ集約します。過去の調査結果そのものを再生成するコマンドではありません。

```bash
bash scripts/setup_tools.sh --with-mdxtools
```

Python 3.10以降、Rust/Cargo、Cコンパイラ、CMake、make、git、curl、および初回のMXC展開用lha／lhasaが必要です。準備方法と固定バージョンは[セットアップ手順](docs/mdx_compiler_setup.md)を参照してください。同じスクリプトを再実行でき、導入したバイナリのハッシュとリビジョンは`.tools/setup_manifest.json`に記録します。

MXC／run68のパスは`--mxc`／`--run68`で指定できます。外部ツールはリポジトリには同梱しません。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input \
  --mxc /path/to/MXC.X --run68 /path/to/run68
```

出力したMDXがコンパイルできることと、MXDRV／MMDSP上で正常に表示・演奏されることは区別してください。MDX→VGMを生成できる場合も、それだけでは元VGMとの音声一致を証明しません。

## PCMを含むVGMからMML・MDX・PDXを生成する

対応するMSM6258入力には、直接レジスタ書き込みと、対応する非圧縮Data Bank／有限DAC Streamがあります。PCMだけの入力も対象です。
OPNAのADPCM-Bも、対応する独立再生区間からMSM6258へ変換して接続できます。再圧縮による近似を許容する`--pcm-policy best-effort`を指定してください。

```bash
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes

# 既知の投影損失を診断付きで許容する場合
python vgm2mml.py input.vgm --outdir outputs/input-best \
  --pcm-policy best-effort --dump-passes

# OPNAのFM・ADPCM-Bから、再生確認用のMDX／PDXをまとめて出力
python scripts/export_mdx.py input.vgm --outdir outputs/listen/opna \
  --no-vgm --pcm-policy best-effort
```

PCMを含む経路では、MMLに加えてMDX／PDXを生成します。可読MMLにはPCM参照を記述しますが、PCM部分のMDX生成は型付き命令列から行い、MMLテキストそのものには依存しません。

- `strict`（既定）：既知の意味損失を伴う投影は停止します。
- `best-effort`：定義済みの近似に限って生成を許可し、失われる情報を診断します。未対応の入力を無条件に変換する設定ではありません。

PCMの符号化バイト列・サンプル同一性と、供給タイミング・STOP／PLAY・panなどの再生情報は区別します。元のPCM IRを維持し、PDXへの投影で失われる情報を記録します。MDX／PDXは一緒にプレイヤーへ渡してください。

**PCMを含むMDXからのVGM再生成は、現時点では利用できません。** MDX／PDXの生成成功と、独立した再生検証は別の結果です。詳細は[PCM/PDX](docs/pcm_pdx.md)を参照してください。

PCMを含む一括出力では、VGM再生成を要求しない`--no-vgm`を指定できます。

```bash
python scripts/export_mdx.py tests/fixtures/public/opm_msm6258 \
  --outdir outputs/listen/opm_msm6258 --no-vgm --pcm-policy best-effort
```

## 互換性と主なオプション

MGSDRV形式への既存変換を使う場合は、ターゲットを明示します。

```bash
python vgm2mml.py input.vgm --target mgs --outdir OUTPUT
```

MDX側の主なオプションは次のとおりです。

| オプション | 内容 |
|---|---|
| `--notation structured` | 音符・制御軌跡・有限反復による表記（既定） |
| `--notation legacy` / `registers` | 互換表記／レジスタ制御表記 |
| `--normalize-lengths` / `--no-normalize-lengths` | structured MDXの長さ補正の有効／無効（structuredは既定ON） |
| `--normalization-ms MS` | 正規化前の短い発音の省略閾値と出力時刻の最大移動量。1 source sample以上（約0.022676ms以上）、既定8 |
| `--no-loops` | 有限反復の生成を無効化 |
| `--psg-model fm\|additive` | PSGからOPMへの音色投影モデル |
| `--psg-gain` / `--scc-gain` | PSG／SCC投影時の音量調整 |
| `--pcm-policy strict\|best-effort` | PCM投影で既知の損失を許容するかを選択 |
| `--dump-passes` | 中間CSV・診断ファイルを保存 |

ここでいう**有限反復**は、VGMヘッダに記録された**曲ループ**とは別です。曲ループのMML出力は未対応です。詳細な制約とその他のオプションは`python vgm2mml.py --help`を参照してください。

## 統計情報レポートの見方

`export_mdx.py`は曲ごとに`tracks/<stem>/<stem>.txt`を生成します。演奏用のMML・MDX・必要なPDXも同じ場所に置き、中間結果やコンパイラ入力は`_diagnostics/`に分けます。全曲の成否は`results.csv`で確認できます。

まず`Export`と`Compiler`を確認してください。`success`はファイル生成の成功であり、元音源との音声一致やMMDSPでの表示・停止を保証する判定ではありません。`Source`は元データ、`Compiled target`は生成MDXの集計です。レジスタへのKey-On／Off要求数、実際のオペレータ状態変化、MDXの音符数はそれぞれ異なる指標です。

`Output normalization`は出力の省略・近似とクロック選択を示します。`source samples`はVGMの44,100Hz時間単位で、音源のPCM符号化バイト数ではありません。1 sampleは約0.02268ms、352 samplesは約7.98msです。

| 項目 | 読み方 |
|---|---|
| `Note normalization` | `applied`なら長さ補正を採用。続く説明に、残る発音や休符の扱いを記載します。 |
| `Normalization parameter` | `--normalization-ms`の設定値。正規化前の発音全体に対する省略閾値と、出力境界の最大移動量を兼ねます。`enabled`は有効／無効です。 |
| `Short-note omission` | `adopted=True`は省略処理を採用したことを示します。実際の省略数は`FM gates`／`PCM playbacks`、省略したFM発音時間は`FM duration`です。数が0なら省略された発音はありません。曲の経過時間と元IRは保持します。 |
| `Coalesced positive control intervals` | 近接する制御境界を同じ出力時刻にまとめた区間数。音符を削除した数ではありません。`maximum output movement`は実際の最大時刻移動量です。 |
| `Coalesced short rests` | 出力で正の長さを失った短い休符の数と元の合計時間。Key-Off／Onの命令順序は保持します。 |
| `Boundary allocation` | `bounded_ordered`なら、最寄りtickへの丸めで発音が消える場合に、設定した最大移動量以内で境界を調整したことを示します。未終了の発音も削除せず、正の長さを残します。FMとPCMは同じ境界・クロックを使います。 |
| `Selected MDX clock` | 採用した1tickの時間とテンポ値。MMLの`@t`がMDXのTimer B値を指定します。4MHz想定では周期は`256 × (256 − tempo byte)`µs。ドライバの実測負荷ではありません。 |
| `Rejected MDX clock candidates` | より粗い候補などを採用できなかった理由。最大時刻誤差や、残す発音・休符区間の消失が制約になります。候補の却下自体は変換失敗ではありません。 |

例えば`Selected MDX clock: 16128 us/tick; tempo byte 193; MML @t193`は、約16.128ms周期の指定です。設定8msに対して最大移動350 samplesは約7.94msなので許容内ですが、候補の誤差362 samplesは約8.21msとなるため採用できません。`example kinds`は抜粋した例で、全区間の種類別集計ではありません。

`PCM assessment`はPCM投影の成否、PDXに格納された符号化データ、周波数対応、再生境界の時刻誤差を別々に報告します。`not available / no PCM projection`は、その結果にPCM投影の評価がないことを示し、単独ではエラーではありません。`Known losses`は既知の損失、`Unverified`／`unmeasured`は未確認事項です。

`Diagnostics`には実行時の失敗理由や取得できなかった統計を記載します。`Missing --mxc tool`ならコンパイラを導入してください。ツール準備後に再実行し、最新の`results.csv`とTXTを確認します。古い失敗レポートは今回の成功結果と区別してください。

## 中間結果と検証

OPNA（YM2608）はReaderとFM State／Segment解析に対応し、通常変換ではOPMへ投影してMDX用MMLを生成します。
SSGはRawと別のSegmentからPSGのFM方式でOPMへ投影し、リズムはRawとして保存・診断します。ADPCM-Bは別のメモリ／再生IRからMSM6258へ変換します。

```bash
python py/vgm_reader.py input.vgm outputs/opna-analysis
```

全チャンネルを含むRaw・State・Segment CSVと未解釈writeのCSVを生成します。
API・フィールド・検証範囲は[OPNAのSegment解析](docs/opna_segments.md)を参照してください。

```bash
python vgm2mml.py input.vgm --outdir OUTPUT --dump-passes
python -m unittest discover -s tests/scripts -v
```

OPMのRaw／State／Segment、制御・構造・タイミング情報、PCMの転送・投影・評価情報を保存し、元のデータと出力結果の対応を確認できます。fixtureは既存の`tests/fixtures/public`および`tests/fixtures/local_only`の構造を維持します。

OPMの往復検証は、外部helperをビルドしたうえで実行します。

```bash
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm \
  --outdir outputs/opm/roundtrip
```

検証経路は`VGM → Segment → MML → MDX → VGM → Segment`です。往復検証の結果と、実機／エミュレータ上の聴感・表示確認は区別します。詳細は[MDXの音価と長さ補正](docs/opm_note_lengths.md)、[PSG/SCC → OPM](docs/psg_scc_opm.md)、[PCM往復検証](docs/pcm_roundtrip_validation.md)を参照してください。

## 構成

- `vgm2mml.py`：通常変換の入口。
- `py/opm_conversion.py`：OPM入力からMDXへの変換手順。
- `py/psg_scc_conversion.py`：PSG／SCC入力からOPM MDXへの変換手順。
- `py/`：音源解析、中間表現、ターゲット生成。
- [scripts](scripts/README.md)：一括出力、診断、往復検証、fixture生成、比較用ツール。
- [設計原則](docs/project_knowledge.md)：変換の原則と制約。

## ライセンス

Copyright (c) 2026 emef2247. Licensed under the [MIT License](LICENSE).

テスト用VGM生成・外部検証に使用するMUCOMVGMもMIT Licenseで、著作権表示は `Copyright (c) 2026 WING` です。使用版のライセンス全文と確認元を[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#mucomvgm-005)に保持しています。MUCOMVGM本体はリポジトリに同梱せず、再配布する場合は同ライセンスの著作権表示・許諾文を含めます。

## 謝辞

本プロジェクトのMDX／VGM出力と往復検証では、以下のツールを利用しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 | 確認した利用条件 |
|---|---|---|
| [MUCOMVGM](https://github.com/wingghost/MUCOMVGM) v0.0.5（WING） | テスト用MUC→VGM生成、およびOPNA FM制御状態の往復検証に利用する外部コンパイラ | MIT |
| MXC v1.01（MFS soft, milk） | MML→MDXコンパイル | フリーウェア・配布自由（付属文書による） |
| [run68x](https://github.com/kg68k/run68x)（TcbnErik・run68の貢献者） | MXCなどHuman68kプログラムの実行 | GPL v2以降 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) 0.2.0（h1romas4） | 明示選択時のMML→MDXコンパイル、およびPCM経路のFM部分 | MIT |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) 0.15.0（h1romas4） | FMのMDX→VGM、PDX構築・PCM参照検査 | MIT |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)（Mitsutaka Okazaki and Contributors） | PSG→OPMの音色・音量対応、およびOPNA FM→OPMのレジスタ対応方式を採用。外部変換結果との比較にも利用しています。 | ISC |
| [mdxtools](https://github.com/vampirefrog/mdxtools)（任意導入） | MDX／PDXの独立検査と逆コンパイル | GPL v3（上流LICENSE） |

OPNA FM→OPMとPSG／SSG→OPMは、vgm-convの対応方式を参照してPython側に実装しています。通常変換で外部のvgm-convコマンドを実行するわけではなく、そのライブラリも不要です。参照した対応方式のISC著作権表示・許諾文はTHIRD_PARTY_NOTICES.mdに保持しています。
b
各ツールの使用版・確認元・著作権表示・配布時の扱いは[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に記録しています。vgm-convのISC全文と、MUCOMVGM／mmlx／soundlogのMIT全文も保持しています。本プロジェクトのMITライセンス表記と併せて、この表示も配布物に含めてください。

セットアップで取得するMXC・run68x・mdxtoolsはローカルの外部ツールで、リポジトリや試聴用出力には同梱しません。これらを別途再配布する場合は各ツールの条件に従います。Rust helperのバイナリを配布する場合は、直接利用するmmlx／soundlogに加えて、推移的依存のライセンス表示も必要です。

外部コンパイラや再生ツールは、用途に応じて別途用意してください。OPMのみのVGM→MML変換はPython側で行います。
