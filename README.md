# x68k_vgm2mml

VGMに記録されたレジスタ操作から音符・音価・音量・音色などの演奏情報を抽出し、X68000向けの構造化されたMML（MDX用）とPCM IRを生成するツールです。対応する入力ではMDX／PDXも一括出力できます。
元のVGMのレジスタ操作を、検査可能な中間表現（State／Segment／PCM IR）として保持し、音楽的に構造化されたMMLへ変換することを目指しています。Python 3.10以降を使用します。

## 使い方

VGMファイルを置いたディレクトリを指定して、一括変換します。

```bash
python scripts/export_mdx.py INDIR --outdir OUTDIR --force
```

VGMの曲全体ループを使わず、1周だけ出力する場合：

```bash
python scripts/export_mdx.py INDIR --outdir OUTDIR --force --no-song-loop
```

既定の設定で、MML・MDX・必要なPDX・変換レポートを生成します。出力先の `results.csv` と各曲のTXTレポートで、成功・失敗や近似・省略の内容を確認できます。

### 主なオプション

| オプション | 説明 |
|---|---|
| `--outdir OUTDIR` | 変換結果の出力先ディレクトリ |
| `--force` | 未対応の演奏要素や容量超過PCMなど、許容された範囲を診断付きで省略して続行 |
| `--no-song-loop` | VGMの曲全体ループを使わず、1周で終了するMDXを生成 |
| `--normalization-ms MS` | 短い発音の省略・時刻補正の基準（既定8ms）。小さいほど細かなイベントを残す |
| `--timeout SECONDS` | 各入力・各処理段階のタイムアウト（既定1200秒） |

`--force` を指定しても、すべての入力が変換できるわけではありません。省略・近似が発生した場合はレポートを確認してください。

## 対応する音源

| VGMの音源 | 主なMDX向け出力 |
|---|---|
| OPM（YM2151） | 演奏構造を抽出してMDX用MMLへ変換 |
| OPNA（YM2608） | FMをOPMへ投影。SSGとADPCM-Bも対応範囲内で変換 |
| PSG／SSG（AY系） | OPMへ投影。PCMへの投影も選択可能 |
| SCC | 波形をOPMのFM／加算合成音色へ近似 |
| DCSG（SN76489系、単体・2チップ） | トーンと対応するノイズをOPMへ近似 |
| MSM6258系PCM | PCM IRを生成し、対応するデータをPDXへ配置 |
| SegaPCM | 再利用可能なサンプルバンクを優先し、必要に応じてミックス方式へ切り替え |

音源の組み合わせやVGM内の制御内容によって対応範囲は異なります。PCMを含むMDXの再生には、対応するPCM拡張ドライバが必要です。

## 変換と再生の注意点

VGMには音符ではなく音源レジスタへの書き込みが記録されているため、MML生成時には発音・音量・音色・音程などを解釈します。異なる音源への投影では近似が発生します。

**MML生成、MDX／PDXへのコンパイル、X68000での再生確認は別の検証段階です。** コンパイルに成功しても、元の音声との一致や実機・エミュレータでの再生成功を保証するものではありません。

PCM容量、MDXトラックサイズ、プレイヤーのメモリ制約などによって変換・再生できない場合があります。曲ループの位置やMDXサイズが原因の場合は、`--no-song-loop` を試してください。

## 詳細資料

- [MDXコンパイラ・再生環境の準備](docs/mdx_compiler_setup.md)
- [FMの演奏構造と状態の整理](docs/opm_performed_structure.md)
- [VGMの曲全体ループ](docs/vgm_loop.md)
- [DCSGからOPMへの変換](docs/dcsg_to_opm.md)
- [SCCからOPMへの投影](docs/scc_fm_projection.md)
- [PSGからPCMへの投影](docs/psg_pcm.md)
- [PCM／PDXの対応範囲と形式](docs/pcm_pdx.md)
- [PCMサンプルバンクと容量削減](docs/pcm_sample_bank_design.md)
- [SegaPCMの解析・投影](docs/segapcm_segments.md)
- [変換の原則と制約](docs/project_knowledge.md)

詳細設定や検証用オプションは、`python scripts/export_mdx.py --help` と各資料を参照してください。

## 構成

- `vgm2mml.py`：単体VGMの解析・MML生成
- `scripts/export_mdx.py`：MML・MDX・PDXの一括生成とレポート出力
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
