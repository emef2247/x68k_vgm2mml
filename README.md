# x68k_vgm2mml

VGMを検査可能な中間表現へ変換し、その中間表現を経由してMMLとPCM IRを生成するツールです。現在のMML出力はMDX形式です。

このプロジェクトの主目的は、VGMのレジスタ操作から導出される情報を、X68000で扱えるMMLとPCM IRとして表現することです。

出力の時間精度は `--normalization-ms`（既定8ms）で調整できます。値を小さくすると細かな発音イベントを保持し、大きくすると短い発音の省略と時刻の近似を広く許容します。元のSegment・PCM IRは保持します。

MDX用MMLでは長い音価を分割して表現します。詳細は[docs/mdx_note_durations.md](docs/mdx_note_durations.md)を参照してください。

Python 3.10以降を使用します。

## 生成されるMMLの確からしさ

VGMには音符そのものではなく、音源への書き込みとその時刻が記録されています。したがって、VGMからMMLを生成する際には、発音・停止・音程・音量・音色の変化を解釈し、MMLで表現可能な時間単位へ変換しています。

MMLの生成に成功したことは、元VGMとの音声一致を保証するものではありません。近似や省略が発生する場合があり、その内容は診断情報やレポートに記録されます。

また、MMLの生成、MDX／PDXへのコンパイル、実際の再生環境での動作は、それぞれ異なる検証段階です。コンパイルに成功した場合でも、再生環境の制約によって正常に演奏できないことがあります。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

ターゲットの既定値はMDX用MMLで、`OUTPUT/input.mdx.mml` を生成します。`--outdir` を省略した場合は入力ファイルと同じディレクトリへ出力します。fixtureの検証には入力と異なる出力先を指定してください。

VGMの実際のコマンドから使用音源を判定し、OPM／PCM、OPNA FM／SSG、または対応するPSG／SCC入力の経路を選択します。未対応の音源・組み合わせ・ストリームは診断情報として報告します。

PSG／SSGは共通の発音・音量run解釈を使い、固定音量のnoise-onlyパート1本をOPMノイズへ近似できます。[対応範囲と中間結果](docs/psg_musical_noise.md)を参照してください。

SCCはMSX側と共通の発音・SW音量run解釈を使い、元の波形をOPMのFM音色や加算合成へ投影します。既定の `fm-additive` では、FM音色を自動探索して加算合成との組み合わせを試みます。従来の `additive` に加え、2chを利用する `additive8`、`fm-fm` も選択できます。

PSGは通常OPMへ変換しますが、連続PCMとして再構築し、X68000に搭載されたOKI MSM6258V向けのADPCMへ変換することもできます。

それぞれの使い方と制約は「[SCCからOPMへの投影](#sccからopmへの投影)」「[PSGをPCMで再生する](#psgをpcmで再生する)」を参照してください。

### 入力と出力

| 入力 | 主な出力 |
|------|------|
| OPM（YM2151） | OPMの状態・SegmentからMDX用MMLを生成 |
| OPM + SegaPCM | OPMのMDX用MMLとSegaPCMの状態・制御Segment・PCM IR。PCMのターゲット投影には`best-effort`を指定 |
| OPNA（YM2608）のFM | Native SegmentからMDX用MMLを生成 |
| OPNAのSSGトーン／限定ノイズ | OPM向けに投影してMDX用MMLを生成 |
| OPNAのADPCM-B（Delta-T） | 元のPCM IRと、MDX向けに投影したPCM IR・PCM参照を含むMML（`best-effort`） |
| PSG／SCC | OPM向け音色・演奏情報へ投影してMDX用MMLを生成。PSGはX68000 ADPCMへの投影も選択可能 |
| 対応するMSM6258系PCM（OPM併用を含む） | PCM IRとPCM参照を含むMDX用MMLを生成 |

OPMのみのMML生成にRustコンパイラは不要です。現行のPCM経路では試聴用MDX／PDXの補助生成も同じ処理内で行うため、外部helperのビルドが必要です。準備方法は[docs/mdx_compiler_setup.md](docs/mdx_compiler_setup.md)を参照してください。

PDXは既定でEX-PDX形式（`--pdx-format ex-pdx`）を生成します。従来形式は `--pdx-format standard` で選択できます。[形式と互換性](docs/pcm_pdx.md#pdx-length-format)を参照してください。

PDXは参照表込みで1,200,000 bytesを上限とします。既定の `--pcm-bank-merge budget96` は、対応するPCM候補から代表音を選び、96枠と総容量の両方に収めます。置換・容量の診断は[PCMバンク削減](docs/pcm_bank_reduction.md)を参照してください。

PCMの出力容量を抑えたい場合は `--pcm-profile low` または `--pcm-profile ultra_low` と `--pcm-policy best-effort` を指定できます。標準設定は維持し、低レートの出力用PCMを生成します。[対応音源・容量と音質の関係](docs/pcm_profiles.md)を参照してください。

SegaPCMは、固定条件の有限サンプルを再利用するバンク方式を優先します。初版の対象外となる途中の設定変更・サンプル内ループなどがある場合は、曲全体を従来のミックス方式へ戻し、理由を記録します。`--segapcm-projection auto|bank|mix` の使い方と制約は[再利用PCMサンプルバンク](docs/pcm_sample_bank_design.md)を参照してください。

## DCSG（SN76489）からMDXへ

単体・2チップのDCSG入力をOPMへ投影できます。最大6トーンと共有ノイズchを使い、既存の音符・反復構造化へ接続します。未対応ノイズや重複区間は`--force`で理由を表示して省略します。[対応範囲と中間結果](docs/dcsg_to_opm.md)を参照してください。

## 確認用VGMの出力

`scripts/export_mdx.py`は既定でMML・MDX・必要なPDXを生成します。MDXの再生結果を確認用VGMにも書き戻したい場合だけ`--vgm`を指定してください。従来の`--no-vgm`は互換用に残していますが、省略できます。

## VGMの曲全体ループ

VGMヘッダーに指定されたループは、既定でMDX用MMLへ引き継ぎます。

MDX用MMLでは `L` で曲ループを表現します。展開方式と対応範囲は[docs/vgm_loop.md](docs/vgm_loop.md)を参照してください。

有限1周で終了させたい場合は `--no-song-loop` を指定してください。これは、MML内の有限反復圧縮を無効にする `--no-loops` とは別の設定です。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input

python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/finite \
  --no-song-loop
```

詳細は[docs/vgm_loop.md](docs/vgm_loop.md)を参照してください。

### SCCからOPMへの投影

SCCはMSX側と共通の発音・SW音量run解釈を使用し、元のState・Segment・32-byte波形を保持したまま、OPM向けの音色・演奏情報へ投影します。

既定の `fm-additive` では、SCCの32-byte波形に対してYM2151のFM音色を探索し、FMと加算合成を組み合わせた音色への近似を試みます。

候補音色はYM2151エミュレーションによるスペクトル測定で評価し、従来の加算合成より誤差が小さい場合に採用します。必要なFM音色バンクは自動生成・キャッシュされます。

利用できる主な音色モデルは次のとおりです。

- `additive` : 1ch・4倍音加算
- `additive8` : 2ch・最大8倍音加算
- `fm-additive` : 1ch FM＋1ch加算（既定）
- `fm-fm` : 2ch FM

`additive8`、`fm-additive`、`fm-fm` は空いているOPM chを利用してSCC波形の近似精度向上を試みます。

OPMのチャンネル数が不足する場合や、FM音色による改善が得られない場合は、従来の1ch加算合成へ戻ることがあります。

SCCのみを比較試聴したい場合は、次のように実行できます。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/scc \
  --scc-only \
  --compiler mmlx
```

8倍音加算モデルを使用する例:

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/scc_additive8 \
  --scc-model additive8 \
  --compiler mmlx
```

FM音色探索を使用する `fm-additive` および `fm-fm` には、WSL上のGCC・NumPyおよび外部YM2151 coreが必要です。`additive` と `additive8` では音色探索を行いません。

SCC波形のFM音色への変換は近似であり、元のSCCと同一の音色を保証するものではありません。特に、基準音程でのスペクトル評価結果が、すべての音程や演奏条件での再現精度を保証するわけではありません。

対応範囲、チャンネル割り当て、音色探索、中間結果については [docs/scc_fm_projection.md](docs/scc_fm_projection.md) を参照してください。

### PSGをPCMで再生する

PSGは通常、OPM向けの音色・演奏情報へ変換しますが、PCMとして再生する方法も選択できます。

`--psg-output pcm` を指定すると、外部AY音源エミュレーションを利用して元のPSGレジスタ操作から連続した音声波形を生成し、X68000のADPCM音源（OKI MSM6258V）向けのデータへ変換します。

この方法では、PSGのトーン、ノイズ、ハードウェアエンベロープをPCM波形として扱うことができます。

元のState・Segmentは変更せず、再生用PCMを別途生成します。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/psg_pcm \
  --psg-output pcm \
  --pcm-policy best-effort \
  --psg-gain 0.8
```

主なオプションは次のとおりです。

| オプション | 内容 |
|------------|------|
| `--psg-output pcm` | PSGの出力先をPCMへ変更。既定の `opm` では従来どおりOPM向けのMMLを生成 |
| `--pcm-policy best-effort` | PCMへの再符号化やサンプリング周波数の変更に伴う近似を許容 |
| `--psg-gain 0.8` | PCMへ変換するPSGの出力音量を調整。SCCなど他の音源との音量バランスに応じて変更可能 |

PCM容量を抑えたい場合は、`--pcm-profile low` または `--pcm-profile ultra_low` も指定できます。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/psg_pcm_low \
  --psg-output pcm \
  --pcm-policy best-effort \
  --pcm-profile low \
  --psg-gain 0.8
```

サンプリング周波数を下げることでPCM容量を削減できますが、高域成分が失われるため音質も低下します。詳細は[PCM出力プロファイル](docs/pcm_profiles.md)を参照してください。

#### 再生上の制約

PSGを連続PCMへ変換すると、演奏時間に応じてPCMデータ量が増加します。

そのため、MML・PCM IRの生成やMDX／PDXへのコンパイルに成功しても、MADRVのトラックバッファ不足などにより再生できない場合があります。

現時点では、グラディウス2の変換結果について、GRA2_02以外の曲でMADRVのトラックバッファ不足を確認しています。

本ツールの主目的は、VGMから構造化されたMMLとPCM IRを生成することです。

生成されたMMLをコンパイル可能な形で提供することを重視しており、再生環境に合わせたMMLの圧縮やPCM容量の最適化については、利用者が生成結果をもとに調整することも想定しています。

変換方法、外部AY coreの準備、対応範囲、中間結果については [PSG→PCM](docs/psg_pcm.md) を参照してください。

## PCMを含むVGMからMML・PCM IRを生成する

対応するMSM6258系入力には、直接レジスタ書き込み、および対応する非圧縮Data Bank／有限DAC Streamがあります。PCMのみの入力も対象です。

OPNAのADPCM-Bも対応範囲内でMML・PCM IRを生成できます。元のPCM IRと、出力先に合わせたPCM投影データは区別して保存します。保持中の音量・パン・速度変更を含む対応範囲と制約は[docs/pcm_interoperability.md](docs/pcm_interoperability.md)を参照してください。

再圧縮による近似を許容する場合は `--pcm-policy best-effort` を指定してください。

```bash
# OPNAのFM・ADPCM-Bから再生確認用MDX／PDXを出力
python scripts/export_mdx.py input.vgm \
  --outdir outputs/listen/opna \
  --pcm-policy best-effort
```

PCM参照を含むMMLとPCM IRが主な出力です。上記の `scripts/export_mdx.py` は試聴用MDX／PDXを一括出力する補助スクリプトです。PCMの型付き命令列とMDX／PDX生成の関係は[docs/pcm_pdx.md](docs/pcm_pdx.md)を参照してください。

- `auto`（既定）: 実際のDACストリーム供給があれば`best-effort`、なければ従来の直接入力経路（`strict`）を選択。直接書き込みとの混在もDAC供給ありとして扱い、選択理由を記録
- `strict`: 既知の意味損失を伴う投影は停止
- `best-effort`: 定義済み近似の範囲内で生成し、失われる情報を診断情報として記録

### SegaPCMを含むVGMからMML・PCM IRを生成する

元のSegaPCM状態・制御情報と再生解析のPCM IRを保持し、MDX向けのPCM投影データを別に生成します。投影には近似を伴うため、`--pcm-policy best-effort` を指定してください。

```bash
# FM＋PCMの試聴用MML／MDX／PDX／TXT生成
python scripts/export_mdx.py INPUT_DIRECTORY \
 --outdir outputs/listen/segapcm --pcm-policy best-effort

# FM部のみのMMLを生成。PCM音声の再生解析・ターゲット投影を省略
python vgm2mml.py input.vgm --outdir outputs/segapcm_fm --fm-only --dump-passes

# 試聴用MML／MDX／TXT生成。scripts/export_mdx.py実行時に--fm-onlyを指定すると、PDXは生成されません。
python scripts/export_mdx.py INPUT_DIRECTORY \
 --outdir outputs/listen/segapcm_fm --fm-only
```

変換の詳細は[docs/segapcm_segments.md](docs/segapcm_segments.md)を参照してください。
SegaPCMの候補サンプルは試聴用WAVとしても保存します。保存先と一覧の見方は[docs/pcm_block_previews.md](docs/pcm_block_previews.md)を参照してください。
MSM6258・Delta-T・SegaPCMは、既定で近いPCMへの置換も使い、PDX向けサンプルを最大96種に収めます。`--pcm-bank-merge similar` は品質条件内の統合、`off` は近似なしです。NumPyが必要です。近似条件と統合結果の見方は[docs/pcm_bank_reduction.md](docs/pcm_bank_reduction.md)を参照してください。

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
| `--normalization-ms MS` | 短い発音の省略閾値と出力時刻の最大移動量（既定8ms） |
| `--fm-state-ms MS` | FM内部の短い音程・音量状態の省略閾値（既定24ms、時刻補正とは独立。[詳細](docs/opm_performed_structure.md)） |
| `--no-loops` | 有限反復の生成を無効化 |
| `--psg-model fm\|additive` | PSGからOPMへの音色投影モデル |
| `--scc-model additive\|additive8\|fm-additive\|fm-fm` | SCC音色モデル（既定fm-additive）。[詳細](docs/scc_fm_projection.md) |
| `--scc-voice-bank FILE` | FM SCCモデルで使う探索済み音色JSON（省略時は自動生成） |
| `--psg-only` / `--psg_only` | PSGだけを出力。元のSCC解析結果は保持 |
| `--scc-only` / `--scc_only` | SCCだけを出力。元のPSG解析結果は保持 |
| `--psg-output opm\|pcm` | PSGの出力先（既定opm）。PCMはbest-effortを指定。[詳細](docs/psg_pcm.md) |
| `--psg-gain` / `--scc-gain` | PSG／SCC投影時の音量調整 |
| `--pcm-policy auto\|strict\|best-effort` | PCM投影で既知損失を許容するか |
| `--pdx-format ex-pdx\|standard` | PDX形式（既定ex-pdx）。[詳細](docs/pcm_pdx.md#pdx-length-format) |
| `--pcm-profile standard\|low\|ultra_low` | PCM出力の容量・音質設定（既定standard）。[詳細](docs/pcm_profiles.md) |
| `--force` | 未対応のPSG／SSG／OPNA機能と容量超過PCMを省略し続行（[docs/opna_force.md](docs/opna_force.md)） |
| `--dump-passes` | 中間CSV・診断ファイルを保存 |

ここでいう **有限反復** は、VGMヘッダーに記録された **曲ループ** とは別です。

VGMヘッダーの曲ループについては、「VGMの曲全体ループ」で説明したとおり出力できます。

有限反復は、構造化されたMML表記において同一パターンを圧縮するための機能です。

詳細な制約とその他のオプションは次を参照してください。

```bash
python vgm2mml.py --help
```

## トラブルシューティング

`scripts/export_mdx.py`のタイムアウトは各入力・各処理段階につき既定1200秒です。`--timeout 秒数`で変更できます。

未対応のPSG／SSG／OPNA機能やPCM容量超過で変換が停止する場合は、`--force`で扱える部分の出力を試せます。未対応のノイズ・ハードウェアエンベロープなどの影響区間や、容量超過のPCMを省略して続行します。元のSegment・PCM IRは保持します。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/force \
  --compiler mmlx --pcm-policy best-effort --force
```

各曲の処理後に、省略・近似した内容をパート、ポート、レジスタ、処理内容、件数、理由の一覧で表示します。チャンネル不足によるパートの省略も確認できます。詳細は各曲のTXTレポートと診断CSV・JSONに保存します。

`--force`は完全な音の再現やMDX生成の成功を保証するオプションではありません。入力破損やコンパイラ制限では引き続き停止します。PCM再符号化などの既知損失を許容する`--pcm-policy best-effort`は別の指定です。適用範囲と診断ファイルの見方は[docs/opna_force.md](docs/opna_force.md)を参照してください。

`scripts/export_mdx.py` と `scripts/verify_opm_mdx_roundtrip.py` の既定コンパイラはmmlxです。MXCを使う場合は `--compiler mxc` を明示してください。PCM経路は引き続きmmlxを使います。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/mmlx \
  --compiler mmlx
```

入力に必要なオプション（`--fm-only` や `--pcm-policy best-effort` など）は、元のコマンドと同じ指定を残してください。

エラーの詳細は出力先の `results.csv` と各曲のTXTレポートで確認できます。MDX形式のトラックオフセット・ループ位置の制限や、プレイヤーのトラックバッファ不足は、コンパイラを変更しても残る場合があります。

`loop start value ... cannot be represented in MDX` などの曲ループ位置のエラーには、`--no-song-loop` を追加して有限1周の出力を試してください。ループ展開を省くことでデータ量が減るため、トラックオフセットの上限超過も解消する場合があります。

```bash
python scripts/export_mdx.py INPUT_DIRECTORY \
  --outdir outputs/listen/finite \
  --compiler mmlx --no-song-loop
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
