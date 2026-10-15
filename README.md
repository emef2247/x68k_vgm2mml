# x68k_vgm2mml

VGMを検査可能な中間表現へ変換し、その中間表現を経由してMMLとPCM IRを生成するツールです。現在のMML出力はMDX形式です。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報を、X68000で扱えるMMLとPCM IRとして表現することです。

出力の時間精度は `--normalization-ms`（既定8ms）で調整できます。値を小さくすると細かな発音イベントを保持し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

MDX用MMLでは長い音価を分割して表現します。詳細は[docs/mdx_note_durations.md](docs/mdx_note_durations.md)を参照してください。

Python 3.10以降を使用します。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

ターゲットの既定値はMDX用MMLで、`OUTPUT/input.mdx.mml` を生成します。`--outdir` を省略した場合は入力ファイルと同じディレクトリへ出力します。fixtureの検証には入力と異なる出力先を指定してください。

VGMの実際のコマンドから使用音源を判定し、OPM／PCM、OPNA FM／SSG、または対応するPSG／SCC入力の経路を選択します。未対応の音源・組み合わせ・ストリームは診断情報として報告します。

### 入力と出力

| 入力 | 主な出力 |
|------|------|
| OPM（YM2151） | OPMの状態・SegmentからMDX用MMLを生成 |
| OPM + SegaPCM | OPMのMDX用MMLとSegaPCMの状態・制御Segment・PCM IR。PCMのターゲット投影には`best-effort`を指定 |
| OPNA（YM2608）のFM | Native SegmentからMDX用MMLを生成 |
| OPNAのSSGトーン | OPM向けに投影してMDX用MMLを生成 |
| OPNAのADPCM-B（Delta-T） | 元のPCM IRと、MDX向けに投影したPCM IR・PCM参照を含むMML（`best-effort`） |
| PSG／SCC | OPM向け音色・演奏情報へ投影してMDX用MMLを生成 |
| 対応するMSM6258 PCM（OPM併用を含む） | PCM IRとPCM参照を含むMDX用MMLを生成 |

OPMのみのMML生成にRustコンパイラは不要です。現行のPCM経路では試聴用MDX／PDXの補助生成も同じ処理内で行うため、外部helperのビルドが必要です。準備方法は[docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md)を参照してください。

## VGMの曲全体ループ

VGMヘッダーに指定されたループは、既定でMDX用MMLへ引き継ぎます。

MDX用MMLでは `L` で曲ループを表現します。展開方式と対応範囲は[docs/vgm_loop.md](docs/vgm_loop.md)を参照してください。

有限1周で終了させたい場合は `--no-song-loop` を指定してください。これは、MML内の有限反復圧縮を無効にする `--no-loops` とは別の設定です。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input --no-vgm

python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/finite \
  --no-vgm \
  --no-song-loop
```

詳細は[docs/vgm_loop.md](docs/vgm_loop.md)を参照してください。

## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを生成する際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表現可能な時間単位へ変換しています。

MMLの生成に成功したことは、元VGMとの音声一致を保証するものではありません。近似や省略が発生する場合があり、その内容は診断情報やレポートに記録されます。

## PCMを含むVGMからMML・PCM IRを生成する

対応するMSM6258入力には、直接レジスタ書き込み、および対応する非圧縮Data Bank／有限DAC Streamがあります。PCMのみの入力も対象です。

OPNAのADPCM-Bも対応範囲内でMML・PCM IRを生成できます。元のPCM IRと、出力先に合わせたPCM投影データは区別して保存します。

再圧縮による近似を許容する場合は `--pcm-policy best-effort` を指定してください。
```bash
# OPNAのFM・ADPCM-Bから再生確認用MDX／PDXを出力
python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/opna \
  --no-vgm \
  --pcm-policy best-effort
```

PCM参照を含むMMLとPCM IRが主な出力です。上記の `scripts/export_mdx.py` は試聴用MDX／PDXを一括出力する補助スクリプトです。PCMの型付き命令列とMDX／PDX生成の関係は[docs/pcm_pdx.md](docs/pcm_pdx.md)を参照してください。

- `strict`（既定）: 既知の意味損失を伴う投影は停止
- `best-effort`: 定義済み近似の範囲内で生成し、失われる情報を診断情報として記録

### SegaPCMを含むVGMからMML・PCM IRを生成する

元のSegaPCM状態・制御情報と再生解析のPCM IRを保持し、MDX向けのPCM投影データを別に生成します。投影には近似を伴うため、`--pcm-policy best-effort` を指定してください。

```bash
# FM＋PCMの試聴用MML／MDX／PDX／TXT生成
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/segapcm --no-vgm --pcm-policy best-effort

# FM部のみのMMLを生成。PCM音声の再生解析・ターゲット投影を省略
python vgm2mml.py input.vgm --outdir outputs/segapcm_fm --fm-only --dump-passes

# 試聴用MML／MDX／TXT生成。scripts/export_mdx.py実行時に--fm-onlyを指定すると、PDXは生成されません。
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/segapcm_fm --fm-only --no-vgm
```

変換の詳細は[docs/segapcm_segments.md](docs/segapcm_segments.md)を参照してください。

`--fm-only` でも元のSegaPCM状態・制御情報は保存します。

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

## トラブルシューティング

`scripts/export_mdx.py` の実行結果が `compilation_failed` になる場合、既定のMXCから `--compiler mmlx` に切り替えると改善することがあります。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/mmlx \
  --no-vgm --compiler mmlx
```

入力に必要なオプション（`--fm-only` や `--pcm-policy best-effort` など）は、元のコマンドと同じ指定を残してください。

エラーの詳細は出力先の `results.csv` と各曲のTXTレポートで確認できます。MDX形式のトラックオフセット・ループ位置の制限や、プレイヤーのトラックバッファ不足は、コンパイラを変更しても残る場合があります。

`loop start value ... cannot be represented in MDX` などの曲ループ位置のエラーには、`--no-song-loop` を追加して有限1周の出力を試してください。ループ展開を省くことでデータ量が減るため、トラックオフセットの上限超過も解消する場合があります。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/finite \
  --no-vgm --compiler mmlx --no-song-loop
```

この指定では曲全体の無限ループが無効になります。MML内の有限反復 `[ ... ]n` による圧縮は維持します。有限1周でもMDXのサイズ制限を超える場合は、エラーが残ります。

## 構成

- `vgm2mml.py` : 通常変換の入口
- `py/opm_conversion.py` : OPM入力の解析とMDX用MML・PCM投影の生成
- `py/psg_scc_conversion.py` : PSG／SCC入力からMDX用MMLへの変換手順
- `py/` : 音源解析、中間表現、ターゲット生成
- `scripts/` : 一括出力、診断、往復検証、fixture生成、比較用ツール
- [docs/project_knowledge.md](docs/project_knowledge.md): 変換の原則と制約

## ライセンス

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

本プロジェクトで参照・利用する第三者コンポーネントのライセンスおよび著作権表示については、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 謝辞

本プロジェクトの開発、検証、比較、およびテスト生成では、以下のツールやプロジェクトを利用または参考にしています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| MXC | MML→MDXコンパイル |
| [run68x](https://github.com/kg68k/run68x) | MXCなどHuman68kプログラムの実行 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) | 明示選択時のMML→MDXコンパイル、およびPCM経路のFM部分 |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) | FMのMDX→VGM、PDX構築・PCM参照検査 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG→OPMの音色・音量対応、およびOPNA FM→OPMのレジスタ対応方式 |
| [mdxtools](https://github.com/vampirefrog/mdxtools) | MDX／PDXの独立検査と逆コンパイル |
| [MUCOMVGM](https://github.com/wingghost/MUCOMVGM) | テスト用MUC→VGM生成、およびOPNA FM制御状態の往復検証 |

OPNA FM→OPMおよびPSG／SSG→OPMは、[vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) の対応方式を参考にPython側へ実装しています。通常変換で外部のvgm-convコマンドやライブラリを必要とするわけではありません。

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

解析とMML・PCM IR生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用します。現行のPCM経路に必要なhelperを含め、準備方法は[docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md)を参照してください。
