# x68k_vgm2mml

VGMから、検査可能な中間表現を経由してMDX用MMLを生成するツールです。現状はym2151,oki6258,scc,psgの一部の音源に対応しています。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報をx68000で扱えるMMLとして取り出すことです。

出力の時間精度は **`--normalization-ms`（既定8ms）** で調整できます。値を小さくすると細かい演奏を残し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

Python 3.10以降を使用します。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

既定のターゲットはMDX用MMLで、`OUTPUT/input.mdx.mml`を生成します。`--outdir`を省略した場合は入力ファイルと同じディレクトリへ出力します。fixtureの検証には入力と異なる出力先を指定してください。

VGMの実際のコマンドから使用音源を判定し、OPM／PCM入力または対応するPSG／SCC入力の経路を選択します。未対応の音源・組み合わせ・ストリームは診断します。

### 入力と出力

| 入力 | 主な出力・変換経路 |
|---|---|
| OPM（YM2151） | OPMの状態・SegmentからMDX用MMLを生成 |
| PSG／SCC | OPM向け音色・演奏に投影してMDX用MMLを生成 |
| 対応するOKIM6258 PCM（OPM併用を含む） | PCM IRとMDX用MMLを生成し、外部helperでMDX／PDXを生成 |

OPMのみのMML生成にRustコンパイラは不要です。PCMを含む通常変換では外部helperのビルドが必要です。

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

対応するOKIM6258入力には、直接レジスタ書き込みと、対応する非圧縮Data Bank／有限DAC Streamがあります。PCMだけの入力も対象です。

```bash
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes

# 既知の投影損失を診断付きで許容する場合
python vgm2mml.py input.vgm --outdir outputs/input-best \
  --pcm-policy best-effort --dump-passes
```

PCMを含む経路では、MMLに加えてMDX／PDXを生成します。可読MMLにはPCM参照を記述しますが、PCM部分のMDX生成は型付き命令列から行い、MMLテキストそのものには依存しません。

- `strict`（既定）：既知の意味損失を伴う投影は停止します。
- `best-effort`：定義済みの近似に限って生成を許可し、失われる情報を診断します。未対応の入力を無条件に変換する設定ではありません。

PCMの符号化バイト列・サンプル同一性と、供給タイミング・STOP／PLAY・panなどの再生情報は区別します。元のPCM IRを維持し、PDXへの投影で失われる情報を記録します。MDX／PDXは一緒にプレイヤーへ渡してください。

**PCMを含むMDXからのVGM再生成は、現時点では利用できません。** MDX／PDXの生成成功と、独立した再生検証は別の結果です。詳細は[PCM/PDX](docs/pcm_pdx.md)を参照してください。

PCMを含む一括出力では、VGM再生成を要求しない`--no-vgm`を指定できます。

```bash
python scripts/export_mdx.py tests/fixtures/public/opm_oki6258 \
  --outdir outputs/listen/opm_oki6258 --no-vgm --pcm-policy best-effort
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
| `Selected MDX clock` | 採用した1tickの時間とテンポ値。MMLの`@t`がMDXのTimer B値を指定します。4MHz想定では周期は`256 × (256 − tempo byte)`µs。ドライバの実測負荷ではありません。 |
| `Rejected MDX clock candidates` | より粗い候補などを採用できなかった理由。最大時刻誤差や、残す発音・休符区間の消失が制約になります。候補の却下自体は変換失敗ではありません。 |

例えば`Selected MDX clock: 16128 us/tick; tempo byte 193; MML @t193`は、約16.128ms周期の指定です。設定8msに対して最大移動350 samplesは約7.94msなので許容内ですが、候補の誤差362 samplesは約8.21msとなるため採用できません。`example kinds`は抜粋した例で、全区間の種類別集計ではありません。

`PCM assessment`はPCM投影の成否、PDXに格納された符号化データ、周波数対応、再生境界の時刻誤差を別々に報告します。`not available / no PCM projection`は、その結果にPCM投影の評価がないことを示し、単独ではエラーではありません。`Known losses`は既知の損失、`Unverified`／`unmeasured`は未確認事項です。

`Diagnostics`には実行時の失敗理由や取得できなかった統計を記載します。`Missing --mxc tool`ならコンパイラを導入してください。ツール準備後に再実行し、最新の`results.csv`とTXTを確認します。古い失敗レポートは今回の成功結果と区別してください。

## 中間結果と検証

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

## 謝辞

本プロジェクトのMDX／VGM出力と往復検証では、以下のツールを利用しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 | 確認した利用条件 |
|---|---|---|
| MXC v1.01（MFS soft, milk） | MML→MDXコンパイル | フリーウェア・配布自由（付属文書による） |
| [run68x](https://github.com/kg68k/run68x)（TcbnErik・run68の貢献者） | MXCなどHuman68kプログラムの実行 | GPL v2以降 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) 0.2.0（h1romas4） | 明示選択時のMML→MDXコンパイル、およびPCM経路のFM部分 | MIT |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) 0.15.0（h1romas4） | FMのMDX→VGM、PDX構築・PCM参照検査 | MIT |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)（Mitsutaka Okazaki and Contributors） | PSG→OPMのFM方式で、AY8910→YM2151の音色パラメータと音量→TL対応表を参考にしました。また、外部変換結果との比較に利用しています。 | ISC |
| [mdxtools](https://github.com/vampirefrog/mdxtools)（任意導入） | MDX／PDXの独立検査と逆コンパイル | GPL v3（上流LICENSE） |

PSG→OPMのSegment処理とターゲット生成は本プロジェクトで実装しており、通常変換にvgm-convのライブラリは不要です。

各ツールの使用版・確認元・著作権表示・配布時の扱いは[第三者の表示](THIRD_PARTY_NOTICES.md)に記録しています。vgm-convのISC全文と、mmlx／soundlogのMIT全文も保持しています。本プロジェクトのMITライセンス表記と併せて、この表示も配布物に含めてください。

セットアップで取得するMXC・run68x・mdxtoolsはローカルの外部ツールで、リポジトリや試聴用出力には同梱しません。これらを別途再配布する場合は各ツールの条件に従います。Rust helperのバイナリを配布する場合は、直接利用するmmlx／soundlogに加えて、推移的依存のライセンス表示も必要です。

外部コンパイラや再生ツールは、用途に応じて別途用意してください。OPMのみのVGM→MML変換はPython側で行います。
