# x68k_vgm2mml

VGMに記録されたレジスタ操作から音符・音価・音量・音色などの演奏情報を抽出し、X68000向けの構造化されたMML（MDX用）とPCM IRを生成するツールです。
Python 3.10以降を使用します。

## 使い方

### VGMファイルを指定してMML及びPCM IRを生成

```bash
# MMLのみ生成
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

もし、MMLの生成からMDXの生成までを自動で行いたい場合は、`scripts/export_mdx.py`(後述）を利用してください。


### VGMファイルを含むディレクトリを指定して、MML,PCM IRとmdx/pdxを一括変換


VGMファイルを置いたディレクトリを指定して、一括変換します。

```bash
#MMLだけではなくMDX/PDXまで一括自動変換。
python scripts/export_mdx.py INDIR --outdir OUTDIR --force
```

VGMの曲全体ループを使わず、1周だけ出力する場合：

```bash
python scripts/export_mdx.py INDIR --outdir OUTDIR --force --no-song-loop
```

MDXの生成にはMXCまたはmmlxなどのMDXコンパイラが必要です。PDXの生成にはsoundlogを利用しています。

これらの環境構築については、[環境構築](docs/mdx_compiler_setup.ja.md) を参照してください。

これら外部ツールを自動でインストールしたい場合は [scripts/setup_tools.sh](scripts/setup_tools.sh) を利用してください。


### 主なオプション

| オプション | 説明 |
|---|---|
| `--outdir OUTDIR` | 変換結果の出力先ディレクトリ |
| `--force` | 未対応の演奏要素や容量超過PCMなど、許容された範囲を診断付きで省略して続行 |
| `--no-song-loop` | VGMの曲全体ループを使わず、1周で終了するMDXを生成 |
| `--psg-output {opm,pcm}` | PSGの演奏情報をOPMまたはPCMのどちらに変換するかを選択 |
| `--nes-balance`／`--no-nes-balance` | NES APU音源にNESミキサーのバランスを補正するマッピングゲインを適用（export_mdxでは既定で有効） |
| `--timeout SECONDS` | 各入力・各処理段階のタイムアウト（既定1200秒） |

`--force` を指定しても、すべての入力が変換できるわけではありません。省略・近似が発生した場合はレポートを確認してください。

## 対応する音源

| VGMの音源 | 主なMDX向け出力 |
|---|---|
| OPM（YM2151） | 演奏構造を抽出してMDX用MMLへ変換 |
| OPNA（YM2608） | FMをOPMへ投影。SSGとADPCM-Bも対応範囲内で変換 |
| PSG／SSG（AY系） | OPMへ投影。PCMへの投影も選択可能 |
| SCC | 波形をOPMのFM／加算合成音色へ近似 |
| NES APU（N2A03） | パルス／三角波／ノイズ／DPCM／FDSをSCCとPSGノイズへ投影し、OPMへ変換。AY系音源との併用にも対応 |
| DCSG（SN76489系、単体・2チップ） | トーンと対応するノイズをOPMへ近似 |
| MSM6258系PCM | PCM IRを生成し、対応するデータをPDXへ配置 |
| SegaPCM | 再利用可能なサンプルバンクを優先し、必要に応じてミックス方式へ切り替え |
| C140 | 全声部をミックスしてPDXへ配置（書き出しの既定）。再利用可能なサンプルバンク方式も選択可能 |

音源の組み合わせやVGM内の制御内容によって対応範囲は異なります。PCMを含むMDXの再生には、対応するPCM拡張ドライバが必要です。

## 変換と再生の注意点

VGMには音符ではなく音源レジスタへの書き込みが記録されているため、MML生成時には発音・音量・音色・音程などを解釈します。異なる音源への投影では近似が発生します。

**MML生成、MDX/PDXへのコンパイル、X68000での再生確認は別の検証段階です。** コンパイルに成功しても、元の音声との一致や実機・エミュレータでの再生成功を保証するものではありません。

PCM容量、MDXトラックサイズ、プレイヤーのメモリ制約などによって変換・再生できない場合があります。曲ループの位置やMDXサイズが原因の場合は、`--no-song-loop` を試してください。

## 構成

- `vgm2mml.py`：単体VGMの解析・MML生成
- `scripts/export_mdx.py`：MML・MDX/PDXの一括生成とレポート出力
- `py/`：音源解析、中間表現、ターゲット生成
- `scripts/`：検証・比較・補助ツール

## ライセンス

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

本プロジェクトで参照・利用する第三者コンポーネントのライセンスおよび著作権表示については、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 謝辞

本プロジェクトの開発、検証、比較、およびテスト生成では、以下のツールやプロジェクトを利用または参考にしています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| MXC | 明示選択時のMML→MDXコンパイル |
| [run68x](https://github.com/kg68k/run68x) | MXCなどHuman68kプログラムの実行 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) | 既定のMML→MDXコンパイル、およびPCM経路のFM部分 |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) | FMのMDX→VGM、PDX構築・PCM参照検査 |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG→OPMの音色・音量対応、およびOPNA FM→OPMのレジスタ対応方式 |
| [mdxtools](https://github.com/vampirefrog/mdxtools) | MDX／PDXの独立検査と逆コンパイル |
| [MUCOMVGM](https://github.com/wingghost/MUCOMVGM) | テスト用MUC→VGM生成、およびOPNA FM制御状態の往復検証 |

OPNA FM→OPMおよびPSG／SSG→OPMは、[vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) の対応方式を参考にPython側へ実装しています。通常変換で外部のvgm-convコマンドやライブラリを必要とするわけではありません。

使用した第三者コンポーネントのバージョン、参照元、著作権表示、ライセンス条件、および再配布時の注意事項は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

解析とMML・PCM IR生成はPythonで実装しています。外部ツールは主にコンパイル、再生確認、比較、およびテスト生成に使用します。現行のPCM経路に必要なhelperを含め、準備方法は[docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md)を参照してください。

---

# x68k_vgm2mml (English)

A tool that extracts musical information — notes, durations, volumes and timbres — from the register operations recorded in a VGM file, and generates structured MML (for MDX) and a PCM IR for the X68000.
Requires Python 3.10 or later.

## Usage

### Generate MML and a PCM IR from a VGM file

```bash
# Generate MML only
python vgm2mml.py INPUT.vgm --outdir OUTDIR
```

If you want MDX generated automatically after the MML, use `scripts/export_mdx.py` (described below).

### Batch-convert a directory of VGM files to MML, PCM IR and mdx/pdx

Place the VGM files in a directory and convert them in one batch.

```bash
# Batch-convert all the way to MDX/PDX, not just MML.
python scripts/export_mdx.py INDIR --outdir OUTDIR --force
```

To output a single pass instead of the VGM's whole-song loop:

```bash
python scripts/export_mdx.py INDIR --outdir OUTDIR --force --no-song-loop
```

Generating MDX requires an MDX compiler such as MXC or mmlx. PDX generation uses soundlog.

See [Environment setup](docs/mdx_compiler_setup.md) for setting these up.

To install the external tools automatically, use [scripts/setup_tools.sh](scripts/setup_tools.sh).

### Main options

| Option | Description |
|---|---|
| `--outdir OUTDIR` | Output directory for the conversion results |
| `--force` | Omit unsupported performance elements, over-capacity PCM and the like within the tolerated range, with diagnostics, and continue |
| `--no-song-loop` | Generate an MDX that ends after one pass instead of using the VGM's whole-song loop |
| `--psg-output {opm,pcm}` | Choose whether PSG performance information is converted to OPM or to PCM |
| `--nes-balance` / `--no-nes-balance` | For NES APU sources, apply mapping gains that compensate the NES mixer balance (enabled by default in export_mdx) |
| `--timeout SECONDS` | Timeout for each input and each processing stage (default: 1200 seconds) |

Even with `--force`, not every input can be converted. If omissions or approximations occur, check the report.

## Supported sound sources

| VGM sound source | Main output for MDX |
|---|---|
| OPM (YM2151) | Extracts the performance structure and converts it to MDX MML |
| OPNA (YM2608) | Projects FM onto OPM. SSG and ADPCM-B are also converted within their supported ranges |
| PSG / SSG (AY family) | Projects onto OPM. Projection onto PCM can also be selected |
| SCC | Approximates waveforms as OPM FM / additive-synthesis voices |
| NES APU (N2A03) | Projects pulse / triangle / noise / DPCM / FDS onto SCC and PSG noise, then converts to OPM. Can also be combined with an AY-family chip |
| DCSG (SN76489 family, single and dual chip) | Approximates tones and the corresponding noise on OPM |
| MSM6258-family PCM | Generates a PCM IR and places the corresponding data into PDX |
| SegaPCM | Prefers a reusable sample bank, switching to the mix method when necessary |
| C140 | Mixes all voices into PDX (the export default). A reusable sample-bank method can also be selected |

The supported range varies with the combination of sound sources and the control content of the VGM. Playing an MDX that contains PCM requires a compatible PCM extension driver.

## Notes on conversion and playback

A VGM records writes to sound-chip registers rather than notes, so MML generation interprets note onsets, volumes, timbres, pitches and so on. Projection onto a different sound source involves approximation.

**MML generation, compilation to MDX/PDX, and playback confirmation on an X68000 are separate verification stages.** A successful compile does not guarantee agreement with the original audio, or successful playback on real hardware or an emulator.

Conversion or playback may fail because of PCM capacity, MDX track size, player memory limits and so on. If the song-loop position or the MDX size is the cause, try `--no-song-loop`.

## Layout

- `vgm2mml.py`: analysis and MML generation for a single VGM
- `scripts/export_mdx.py`: batch generation of MML and MDX/PDX, with report output
- `py/`: sound-source analysis, intermediate representations, target generation
- `scripts/`: verification, comparison and auxiliary tools

## License

Copyright (c) 2026 emef2247.

Licensed under the [MIT License](LICENSE).

For the licenses and copyright notices of the third-party components this project references or uses, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgements

The following tools and projects were used or referenced in the development, verification, comparison and test generation of this project. Thanks to their developers, maintainers and contributors.

| Project | Use in this repository |
|---|---|
| MXC | MML to MDX compilation when explicitly selected |
| [run68x](https://github.com/kg68k/run68x) | Running Human68k programs such as MXC |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx) | Default MML to MDX compilation, and the FM part of the PCM route |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog) | FM MDX to VGM, PDX construction and PCM reference checking |
| [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) | PSG to OPM timbre/volume correspondence, and the OPNA FM to OPM register correspondence method |
| [mdxtools](https://github.com/vampirefrog/mdxtools) | Independent inspection and decompilation of MDX / PDX |
| [MUCOMVGM](https://github.com/wingghost/MUCOMVGM) | Generating MUC to VGM for tests, and round-trip verification of OPNA FM control state |

The OPNA FM to OPM and PSG / SSG to OPM conversions implement correspondence methods in Python with reference to [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv). Normal conversion does not require the external vgm-conv command or library.

The versions, sources, copyright notices, license terms and redistribution notes of the third-party components used are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Analysis and the generation of MML and the PCM IR are implemented in Python. External tools are used mainly for compilation, playback confirmation, comparison and test generation. For how to prepare everything, including the helpers the current PCM route requires, see [docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md).
