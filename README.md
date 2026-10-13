# x68k_vgm2mml

VGMを検査可能な中間表現へ変換し、その中間表現を経由してMDX用MMLを生成するツールです。現状はYM2151、YM2608のFM、MSM6258、SCC、PSGの一部の音源に対応しています。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報を、X68000で扱えるMMLとして表現することです。

出力の時間精度は `--normalization-ms`（既定8ms）で調整できます。値を小さくすると細かな発音イベントを保持し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

生成するMDX用MMLは、1命令の音価が256クロックを超えないよう分割します。長い音符はタイでつないで再発音を避け、休符は総クロック数を保って分割します。これはMXCの音長上限への対応であり、時間正規化や音程の変更ではありません。

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
| OPM + SegaPCM | Native State／制御Segmentを保存。`--fm-only` でOPM部だけをMDX用MML／MDXへ出力（SegaPCM音声は省略、PDX未対応） |
| OPNA（YM2608）のFM | Native SegmentからOPM（4MHz）へ投影し、既存OPM経路でMDX用MMLを生成 |
| OPNAのSSGトーン | 既存PSGのFM方式でOPMへ投影。曲全体でFMを優先し、残りのOPMチャンネルへ割り当て |
| OPNAのADPCM-B（Delta-T） | 元のIRを保持し、MSM6258へ再圧縮して既存Pトラック／PDX経路へ接続（`best-effort`） |
| PSG／SCC | OPM向け音色・演奏情報へ投影してMDX用MMLを生成 |
| 対応するMSM6258 PCM（OPM併用を含む） | PCM IRとMDX用MMLを生成し、外部helperでMDX／PDXを生成 |

OPMのみのMML生成にRustコンパイラは不要です。PCMを含む通常変換では外部helperのビルドが必要です。

### SegaPCM入り入力のFM部を先に確認する

SegaPCMはVGMのメモリ書き込み（C0）とROMブロック（80）を読み込み、16チャンネルのNative State／制御Segmentを保存します。これらは書き込みから分かる設定区間です。内部で進む再生アドレス、自然終了、実際に音が鳴る区間のエミュレーションはまだ含みません。SegaPCMからPDXへの変換は次の対応です。

通常の変換コマンドでは解析結果のみを出力します。MDX側のFM再生を先に検証する場合は、PCMを除外することを明示する `--fm-only` を指定します。

```bash
# Native OPM／SegaPCMの解析のみ
python vgm2mml.py input.vgm --outdir outputs/segapcm_source

# FM部のMML生成（ループ・音程補正・時間正規化は既存OPM処理）
python vgm2mml.py input.vgm --outdir outputs/segapcm_fm --fm-only --dump-passes

# 試聴用MML／MDX／TXT生成。PDXは生成しない
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/segapcm_fm --fm-only --no-vgm
```

`--fm-only` はOPMとSegaPCMを併用する入力専用です。TXTとconversion JSONにSegaPCMの除外を明記します。`--pcm-policy best-effort` はこの除外の代わりにはなりません。未対応の別音源・ストリームや壊れたコマンドは引き続きエラーにします。

この経路のNative CSV／ROM payload／解析JSONは `--dump-passes` がなくても保存します。exportスクリプトでは `_diagnostics` 以下に残し、試聴用の `tracks` へMML・MDX・TXTを配置します。保存したROM payloadは生成物であり、Gitへ追加しないでください。

詳細は[docs/segapcm_segments.md](docs/segapcm_segments.md)を参照してください。FM部だけならPDXを必要としませんが、MDX生成成功と実機の再生・表示確認は別です。

OPNA FM→OPMには [vgm-conv](https://github.com/digital-sound-antiques/vgm-conv) のOPN→OPM方式を採用しています。音色・operator・キー・左右出力を対応付け、元の11bit FNUM/BLOCKから既存のKC/KF処理で4MHz向けの音程を生成します。外部の[vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)コマンド実行は不要です。参照実装のISC表示は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#vgm-conv) に保持しています。

OPNAのFM・SSGをMDXへ投影し、ADPCM-Bは別のPCM経路へ渡します。SSGには既存PSGと同じFM音色・音量対応・発音推定を使用します。曲全体で使用チャンネルを調べ、FMを優先してOPMの8チャンネルへ割り当てます。残りをSSGの番号順に使用し、割り当て可能数を超えたSSGチャンネルは省略し、その旨を診断情報へ記録します。

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

## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを生成する際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表現可能な時間単位へ変換しています。

MMLの生成に成功したことは、元VGMとの音声一致を保証するものではありません。近似や省略が発生する場合があり、その内容は診断情報やレポートに記録されます。

## PCMを含むVGMからMML・MDX・PDXを生成する

対応するMSM6258入力には、直接レジスタ書き込み、および対応する非圧縮Data Bank／有限DAC Streamがあります。PCMのみの入力も対象です。

OPNAのADPCM-Bも、対応する独立再生区間からMSM6258へ変換して接続できます。

再圧縮による近似を許容する場合は `--pcm-policy best-effort` を指定してください。
```bash
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


## TROUBLE SHOOTING

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
- `py/opm_conversion.py` : OPM入力からMDXへの変換手順
- `py/psg_scc_conversion.py` : PSG／SCC入力からOPM MDXへの変換手順
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

本プロジェクトによるVGM→MML変換そのものはPythonのみで動作し、上記の外部ツールを必要としません。

これらのツールは主にコンパイル、再生確認、比較、およびテスト生成のために利用または参照しています。関連する補助スクリプトを利用する場合のみ、用途に応じて別途用意してください。
