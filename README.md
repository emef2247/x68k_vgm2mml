# x68k_vgm2mml

X68000向けのOPM/YM2151 VGMを、検査可能な中間表現を経由してMDX MMLへ変換します。
通常変換の入口は `vgm2mml.py` です。Python 3.10以降を使用します。
PSG/SCCのVGMをOPM向けに変換し、MDX MMLを生成する経路もあります。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir outputs/input
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes
```

既定は `--target mdx`（ネイティブOPM入力）で、`outputs/input/input.mdx.mml` を生成します。
`--outdir` を省略すると入力ファイルと同じディレクトリに出力します。
fixtureの検証には必ず別の出力先を指定してください。MML生成にRustコンパイラは不要です。
ネイティブMDX経路の対象はOPMです。PCM/PDXの変換・再現は対象に含まれません。

| 選択 | 入力と出力 |
|---|---|
| `--target mdx`（既定） | OPM/YM2151 → MDX MML |
| `--target opm` | PSG/SCC → OPM MDX MML（PSGはFMモデル） |
| `--target opm-additive` | PSG/SCC → OPM MDX MML（PSGは加算モデル） |

ネイティブOPM入力には `--target mdx`、PSG/SCC入力には `--target opm` を使用します。

## MDXオプションと中間結果

以下はOPM/YM2151入力の `--target mdx` に対するオプションです。

- `--notation structured`：音符・制御軌跡・有限ループを使った表記（既定）。
- `--notation legacy`：以前のハイブリッド表記。
- `--notation registers`：レジスタ制御による再生表記。
- `--track-layout channels`：A〜Hのチャンネル別出力（既定）。
- `--track-layout conductor`：単一制御トラック。`--notation registers`と併用。
- `--no-loops`：有限ループの生成を無効化。
- `--normalize-lengths`：構造化MDXの長さを、推定した共通クロックに補正。既定では補正しません。
- `--title "曲名"`：タイトルを指定。省略時はGD3、次にファイル名。`--gd3-language ja|en`で優先言語を指定。
- `--dump-passes` / `--debug`：中間CSVと診断レポートを保存。

OPMではraw register CSV、state CSV、統合Segment CSV、`*.mdx.controls.csv`、
`*.mdx.structure.*`（構造化表記時）、`*.mdx.timing.json`を確認できます。
Raw → State → Segment → Targetの境界とsource sample情報を維持します。
各トラックは `/* Track A */` などのコメントで始まります。音符の長さは正確に表せる音価・付点を優先し、残りは `%N` で表します。長音はタイで接続します。
オクターブと音量は、直前の値が既知で差が1〜2段なら、長くならない相対表記 `<` / `>` / `(` / `)` を使います。ループ先頭や音色再ロード後など、状態を確定できない箇所には必要な絶対指定を残します。
長さの補正は次のように指定します。

```bash
python vgm2mml.py input.vgm --outdir outputs/input --normalize-lengths --dump-passes
```

補正前のMMLと補正量・採用理由を保存し、元のSegment・レジスタ値・時刻を維持します。
全境界の補正量や順序を確認できない曲は通常出力に戻します。詳細は [MDXの音価と長さ補正](docs/opm_note_lengths.md) を参照してください。
MDX出力はマクロ化を行いません。有限反復には対応していますが、VGMヘッダーの曲ループ宣言を
MMLの曲ループとして生成する処理は未対応です。宣言された境界は中間CSVに記録します。
既存MDXから独立した構造化MMLを得る手順と検証範囲は [MDX参照MML](docs/mdx_reference_mml.md) を参照してください。

## PSG/SCC → OPM

```bash
python vgm2mml.py input.vgm --target opm --outdir outputs/input-opm --dump-passes
python vgm2mml.py input.vgm --target opm --psg-model additive --outdir outputs/input-additive --dump-passes
```

既定のPSG音色はFM/フィードバックモデルです。`--psg-model additive`で加算モデルを選べます。
SCCは波形から求めた加算モデルを使用します。`--psg-gain`と`--scc-gain`で音量を調整できます。

この経路も既定で構造化MDX MMLを出力します。可聴状態の開始・終了から発音と休符を推定し、
投影OPM VGMを通常のOPM→MDX生成パスへ渡します。音程・音量の変化だけでは再発音しません。
推定発音の導入により、従来の保持方式とは発振位相が変わります。
`--notation registers`で従来の保持／レジスタ制御表記を選べます。
現在、全無音入力は構造化経路でエラーになる残件があります。
PSGのノイズ・トーンとノイズの混在・ハードウェアEGは
未対応で、対象の動作を含む入力はエラーになります。
音程の範囲制限と近似内容を含む詳細は [PSG/SCC → OPM](docs/psg_scc_opm.md) を参照してください。
`--dump-passes`では、ソースSegment、従来の投影、推定した発音計画を保存します。
`projected_opm/`には中間OPM VGM、元データへの対応表、通常OPM生成パスの状態・構造CSVを保存します。
音程・音量・muteの変化を、元のソース行と生成された制御に対応付けて確認できます。

## MML・MDX・VGMを生成して聴く

MDXと、そのMDXを再生したOPM VGMを生成するには、外部生成ツールを使います。
初回は次のコマンドでビルドしてください。

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
```

単一のPSG/SCC入力から3ファイルを生成する例です。OPM入力の場合は
`--target opm`を`--target mdx`に変更します。

```bash
python vgm2mml.py input.vgm --target opm --outdir outputs/input

scripts/mdx_fixture_generator/target/release/mdx-fixture-generator \
  outputs/input/input.mdx.mml \
  outputs/input/input.mdx \
  outputs/input/input.vgm \
  --max-ticks 1000000
```

`--dump-passes`を付けなければ、MML・MDX・VGMの3ファイルを生成します。
既存のCSVなどは自動削除しません。`--max-ticks`は再生tick数の上限です。
現在のPSG出力の`@t255`では1000000 ticksが約256秒分で、より長い曲には上限を増やします。
元VGMとの比較検証は行いません。生成MDXをX68000エミュレータ上のMMDSPで再生して、
音とGUI表示を確認できます。生成VGMは同じMDXから出力したOPM VGMです。

### フォルダを一括出力する

[export_mdx.py](scripts/export_mdx.py)は、指定フォルダ以下の`.vgm`と`.vgz`を再帰的に処理します。
変換本体は`vgm2mml.py`、MDX/VGM生成は上記の外部ツールを使います。

```bash
# PSG/SCC入力
python scripts/export_mdx.py tests/fixtures/public/psg \
  --target opm --outdir outputs/listen/psg

# ネイティブOPM入力
python scripts/export_mdx.py tests/fixtures/public/opm/from_mdx \
  --target mdx --outdir outputs/listen/opm
```

入力は単一ファイルでも指定できます。入力と出力には別のフォルダを指定してください。
入力の相対パスを`tracks/`以下に保ち、曲ごとのフォルダ名には元の拡張子も残します。
同名の`.vgm`と`.vgz`は別フォルダになります。

```text
outputs/listen/psg/
  results.csv
  tracks/
    volume_sweep/
      volume_sweep.vgm/
        volume_sweep.mdx.mml
        volume_sweep.mdx
        volume_sweep.vgm
```

成功曲のフォルダには3ファイルだけを生成します。`results.csv`には各入力の成否と出力パスを記録し、
失敗時のログは`_errors/`に保存します。変換できない曲があっても残りを処理し、1件でも失敗した場合は
終了コード1を返します。途中まで生成できたMML/MDXは診断用に残ります。
再実行では同じ曲の既存3ファイルを置き換えます。

再生tick上限は実際のVGMの待ち時間から自動計算します。`--max-ticks N`で指定することもできます。
`--generator PATH`で外部ツールを、`--timeout N`で各処理の制限秒数を指定できます（既定180秒）。
`--psg-model`、`--psg-gain`、`--scc-gain`、`--opm-pitch-policy`は変換本体へ渡します。
PSGのノイズ・ハードウェアEGなどの未対応動作は、一括出力でも失敗として記録されます。

## 検証

```bash
python -m unittest discover -s tests/scripts -v
```

WAV解析のテストにはNumPyが必要です。外部MDXコンパイラを使う検証は別途実行します。

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm --outdir outputs/opm/roundtrip
```

往復検証は [外部fixture generator](scripts/mdx_fixture_generator/README.md) を利用します。
このツール内で、MML → MDXのコンパイルには **mmlx 0.2.0**、MDXのコマンド実行とVGM出力には **soundlog 0.15.0** を使います。
mdxtoolsの `mdx2mml` は既存MDXから独立した参照MMLを作るために、`mdxdump` は構造・メタデータ確認に使います。
fixtureは既存の `tests/fixtures/public` と `tests/fixtures/local_only` に置き、構造を維持します。
非公開fixtureと生成物はGit管理対象外です。

## 構成

- `vgm2mml.py`：通常変換の入口。
- `py/opm_conversion.py`：OPM入力からMDXへの変換手順。
- `py/psg_scc_conversion.py`：PSG/SCC入力からOPM MDXへの変換手順。
- `py/`：チップ解析・中間表現・ターゲット生成。
- [scripts](scripts/README.md)：一括出力、診断、往復検証、fixture生成、比較用ツール。
- [設計原則](docs/project_knowledge.md)。

## 謝辞

本プロジェクトのMDX/VGM出力と往復検証では、以下のライブラリを利用しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx)（h1romas4/chipstream） | MML → MDXコンパイル。聴き比べ用出力・往復検証・公開fixture生成で使用。 |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog)（h1romas4/chipstream） | MDX → VGM変換。聴き比べ用出力・往復検証・公開fixture生成で使用。 |

外部コンパイラ・再生ツールはMDX/VGM出力や開発・検証用の任意依存です。通常のVGM → MML変換はPython側の実装で行います。

