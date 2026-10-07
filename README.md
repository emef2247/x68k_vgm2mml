# x68k_vgm2mml

X68000向けのOPM/YM2151 VGMを、検査可能な中間表現を経由してMDX MMLへ変換します。
通常変換の入口は `vgm2mml.py` です。Python 3.10以降を使用します。
PSG/SCC/OPLLからMGSDRV MMLへの互換経路も維持しています。

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
| `--target mgs` | PSG/SCC/OPLL → MGSDRV MML |
| `--target opm` | PSG/SCC → OPM MDX MML（PSGはFMモデル） |
| `--target opm-additive` | PSG/SCC → OPM MDX MML（従来の加算モデル） |

`--target opm` は継承したチップ変換経路です。ネイティブOPM入力は `--target mdx` を使用します。
PSGのノイズ・ハードウェアEGなど、チップ変換の未対応動作はエラーになります。
詳細は [PSG/SCC → OPM](docs/psg_scc_opm.md) を参照してください。

## MDXオプションと中間結果

- `--notation structured`：既存の音符・軌跡・有限ループ生成（既定）。
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
現在の処理には発音単位・制御軌跡・共通ループ計画が既にあります。
今後のMDX見直しは、MGSDRVと共有できる処理を活用し、具体的な出力上の問題を確認して進めます。
今回のMDX処理ではマクロ化を対象外とし、有限反復・曲ループは引き続き対象にします。
既存MDXから独立した構造化MMLを得る手順と検証範囲は [MDX参照MML](docs/mdx_reference_mml.md) を参照してください。

## MGSDRV互換経路

```bash
python vgm2mml.py input.vgm --target mgs --outdir outputs/input-mgs --dump-passes
```

`input.mml`を生成します。`--raw-ticks`、`--normalize-lengths`、`--alloc`、
`--legacy-loops`、`--legacy-macros`などの既存オプションを維持します。
[互換経路の詳細](docs/mgs_compatibility.md)を参照してください。
`--vgmticks --dump-passes`で元のサンプル時刻も検査できます。

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
- `py/opm_conversion.py`、`py/psg_scc_conversion.py`：共有の変換手順。
- `py/`：チップ解析・中間表現・ターゲット生成。
- [scripts](scripts/README.md)：診断、往復検証、fixture生成、比較用ツール。
- [設計原則](docs/project_knowledge.md)、[現在の引き継ぎ](handoffs/current.md)。

## 謝辞

本プロジェクトのMDX往復検証では、以下のライブラリを利用しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx)（h1romas4/chipstream） | MDX往復検証・公開fixture生成でのMML → MDXコンパイル。 |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog)（h1romas4/chipstream） | MDX往復検証・公開fixture生成でのMDX → VGM変換。 |

外部コンパイラ・再生ツールは開発・検証用の任意依存です。通常のVGM → MML変換はPython側の実装で行います。

