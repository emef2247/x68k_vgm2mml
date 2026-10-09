# x68k_vgm2mml

X68000向けのOPM/YM2151 VGMを、検査可能な中間表現を経由してMDX MMLへ変換します。
通常変換の入口は `vgm2mml.py` です。Python 3.10以降を使用します。
直接書き込み型のOKIM6258入力には、標準PCMトラックとPDXの生成経路があります。
PSG/SCCのVGMをOPM向けに変換し、MDX MMLを生成する経路もあります。

## 通常変換

```bash
python vgm2mml.py input.vgm --outdir OUTPUT
```

既定の出力形式はMDXで、`OUTPUT/input.mdx.mml`を生成します。
実際に使われたVGMコマンドから、OPM/PCM入力とPSG/SCC→OPM投影の標準経路を選びます。
未使用のclock宣言だけでは経路を変更しません。未対応の使用音源・組み合わせ・ストリームは明示的に診断します。
`--outdir` を省略すると入力ファイルと同じディレクトリに出力します。
fixtureの検証には必ず別の出力先を指定してください。OPMのみのMML生成にRustコンパイラは不要です。
PCMを含む入力では、下記の外部helperをビルドしてMDXとPDXも生成します。

| 入力 | 自動選択する経路 |
|---|---|
| OPM/YM2151 | 通常のOPM → structured MDX MML |
| 対応するOKIM6258（OPMとの併用も可） | 共通clockによるMDX MML／MDX＋PDX |
| 対応するPSG/SCC | PSGはFM、SCCは加算モデルでOPMへ投影 → 通常のstructured MDX生成 |

structured MDXでは安全な長さ補正を既定で試みます。採用できない場合もstructuredのまま、
補正前のclock/timing projectionを使います。`input.mdx.normalization.json`に採否・理由・選択clockを、
`input.conversion.json`に音源検出・経路・モデルを記録します。
同名の参照MDX／PDXは通常のMML変換で削除しません。前回のPCM生成記録とhashが一致する
成果物だけを再実行時に消去します。所有を確認できないMDX／PDXがPCM生成先にある場合は、
別の`--outdir`を指定してください。保存した既存ファイルは診断に記録し、今回の生成物とは扱いません。
`--title "曲名"`でタイトルを指定でき、省略時はGD3、次にファイル名を使います。
`--gd3-language ja|en`でGD3の優先言語を指定できます。

## Compatibility options

MGSDRV形式を使う場合は明示します。既存のPSG/SCC/OPLL互換処理と補正OFFの既定値を維持します。

```bash
python vgm2mml.py input.vgm --target mgs --outdir OUTPUT
```

`--name`、`--alloc`、`--raw-ticks`、`--sync-min-gap`、`--psg-input`、`--scc-input`、
`--vgmticks`、`--legacy-macros`、`--legacy-loops`はMGSDRV用です。
`--legacy-loops`は旧ループ／エンベロープ処理の選択で、MDXの有限反復圧縮とは別の機能です。
`--enhance-macros`は既定ONのためdeprecatedです。

旧`--target opm`／`opm-additive`は警告付き互換別名として残します。
前者は通常のMDX指定、後者は`--psg-model additive`へ移行してください。
モデル別gainとpitch policy、registersの従来保持方式は維持しますが、structuredの補正は既定ONになります。

## Advanced MDX options

通常は指定不要です。適用できるsourceとnotationは`--help`でも確認できます。

- `--notation structured`：音符・制御軌跡・有限ループを使った表記（既定）。
- `--notation legacy`：以前のハイブリッド表記。
- `--notation registers`：レジスタ制御による再生表記。
- `--track-layout channels`：A〜Hのチャンネル別出力（既定）。
- `--track-layout conductor`：単一制御トラック。`--notation registers`と併用。
- `--no-loops`：有限ループの生成を無効化。
- `--normalize-lengths`／`--no-normalize-lengths`：structured MDXのtarget-clock補正を有効／無効化。既定ON。legacy/registersでは既定OFF。
- `--psg-model fm|additive`：PSG→OPMのモデルを選択。既定FM、SCCは加算モデル。
- `--psg-gain`／`--scc-gain`：PSG/SCC→OPMの投影音量を調整。
- `--opm-pitch-policy clamp|error`：PSG/SCC投影の音程範囲方針。既定FM=clamp、加算=error。
- `--pcm-policy strict|best-effort`：PCMのMDX投影における既知損失の扱い。既定strict。補正の採否とは独立。

## Diagnostic / development optionsと中間結果

```bash
python vgm2mml.py input.vgm --outdir OUTPUT --dump-passes
```

`--dump-passes`で中間CSVと診断レポートを保存します。`--debug`はMDXでは同じ診断保存、
MGSDRVでは全チップ別MMLの保存も行います。`--pcm-generator PATH`は外部PCM helperの配置指定です。

OPMではraw register CSV、state CSV、統合Segment CSV、`*.mdx.controls.csv`、
`*.mdx.structure.*`（構造化表記時）、`*.mdx.timing.json`を確認できます。
Raw → State → Segment → Targetの境界とsource sample情報を維持します。
各トラックは `/* Track A */` などのコメントで始まります。音符の長さは正確に表せる音価・付点を優先し、残りは `%N` で表します。長音はタイで接続します。
オクターブと音量は、直前の値が既知で差が1〜2段なら、長くならない相対表記 `<` / `>` / `(` / `)` を使います。ループ先頭や音色再ロード後など、状態を確定できない箇所には必要な絶対指定を残します。
長さ補正を明示的に無効化する場合は次のように指定します。

```bash
python vgm2mml.py input.vgm --outdir OUTPUT --no-normalize-lengths --dump-passes
```

補正量・採否理由をJSONに保存し、採用時は`--dump-passes`で補正前MMLも保存します。
元のSegment・レジスタ値・時刻を維持します。
全境界の補正量や順序を確認できない曲は同じstructuredの補正前投影を使います。
PCMを含む場合も、共有clockの安全性を確認できない補正は見送り、補正ONだけを理由にエラーにしません。
詳細は [MDXの音価と長さ補正](docs/opm_note_lengths.md) を参照してください。
MDX出力はマクロ化を行いません。有限反復には対応していますが、VGMヘッダーの曲ループ宣言を
MMLの曲ループとして生成する処理は未対応です。宣言された境界は中間CSVに記録します。
既存MDXから独立した構造化MMLを得る手順と検証範囲は [MDX参照MML](docs/mdx_reference_mml.md) を参照してください。

## PSG/SCC → OPM

```bash
python vgm2mml.py input.vgm --outdir outputs/input-opm --dump-passes
python vgm2mml.py input.vgm --psg-model additive --outdir outputs/input-additive --dump-passes
```

既定のPSG音色はFM/フィードバックモデルです。`--psg-model additive`で加算モデルを選べます。
SCCは波形から求めた加算モデルを使用します。`--psg-gain`と`--scc-gain`で音量を調整できます。

この経路も既定で構造化MDX MMLを出力します。可聴状態の開始・終了から発音と休符を推定し、
投影OPM VGMを通常のOPM→MDX生成パスへ渡します。音程・音量の変化だけでは再発音しません。
推定発音の導入により、従来の保持方式とは発振位相が変わります。
`--notation registers`で従来の保持／レジスタ制御表記を選べます。
保持方式は内部のcompatibility projection modeとして分離し、publicの発音方式オプションは追加していません。
既存の無発音OPLL初期化や未宣言SCCのゼロ音量初期化は、コマンド数と理由を診断に残します。
全無音入力では架空の発音を作らず、共通の終端まで休符を出力します。
PSGのノイズ・トーンとノイズの混在・ハードウェアEGは
未対応で、対象の動作を含む入力はエラーになります。
音程の範囲制限と近似内容を含む詳細は [PSG/SCC → OPM](docs/psg_scc_opm.md) を参照してください。
`--dump-passes`では、ソースSegment、従来の投影、推定した発音計画を保存します。
`projected_opm/`には中間OPM VGM、元データへの対応表、通常OPM生成パスの状態・構造CSVを保存します。
音程・音量・muteの変化を、元のソース行と生成された制御に対応付けて確認できます。

## MML・MDX・VGMを生成して聴く

MML・MDX・そのMDXを再生したOPM VGMをまとめて生成するには、
`scripts/export_mdx.py`を使います。FMのみの入力では、既定のコンパイラは
**MXC（MXC.X）**です。MXCの実行には[run68x](https://github.com/kg68k/run68x)の
`run68`を使い、生成MDXの検査とVGM出力には次のhelperを使います。

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
```

MXC.Xは[MDX_TOOL.lzh](https://nfggames.com/X68000/Mirrors/x68pub/x68tools/SOUND/MXDRV/MDX_TOOL.lzh)
に含まれています。MXCとrun68をPATHに置くか、`--mxc`と`--run68`で指定してください。
この作業環境では`outputs/research/mxc_tools/extracted/mxc.x`と
`outputs/research/run68x/build/run68`も自動検出します。ツール本体はGitに含めません。

単一のOPMまたはPSG/SCC入力からMML・MDX・VGMを生成する例です。

```bash
python scripts/export_mdx.py input.vgm --outdir outputs/listen/input \
  --mxc /path/to/MXC.X --run68 /path/to/run68
```

曲のフォルダにMML・MDX・VGMを生成し、成否と使用したコンパイラを`results.csv`に記録します。
元VGMとの比較検証は行いません。生成MDXをX68000エミュレータ上のMMDSPで再生して、
音とGUI表示を確認できます。VGMはsoundlogによる同じMDXの再生結果です。
ファイル生成の成功と、MXDRV／MMDSP上の表示・再生確認は区別してください。

従来のmmlxを使う場合は、`--compiler mmlx`を明示します。MXCの失敗時に自動で
mmlxへ切り替えることはありません。helper自体のMMLを渡す3引数モードは、
引き続きmmlxを使用します。

### PCMを含むVGMからMML・MDX・PDXを生成する

上記のhelperをビルドしたうえで、通常の変換入口を使います。PCMだけの入力も対応します。

```bash
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes

# 確認済みの途中pan損失を診断付きで許容する場合
python vgm2mml.py input.vgm --outdir outputs/input-best \
  --pcm-policy best-effort --dump-passes
```

一度の変換で `input.mdx.mml`、`input.mdx`、`input.pdx`を生成します。
OPMは通常の構造化MML経路を使い、PCMは型付き命令列から標準9トラックMDXへ直接組み立てます。
可読MMLにも `#pcmfile "input.pdx"` とPトラックを出力しますが、PCMのMDX生成はこのテキストに依存しません。
MDXとPDXを一緒にX68000のプレイヤーへ渡してください。
helperを別の場所に置く場合は、変換時に `--pcm-generator PATH` を指定します。

初期対応は、直接 `0xB7` 書き込みによる4-bit／10-bit出力のOKIM6258、一つの物理PCMチャンネル、
標準F0〜F4と一致する速度、PDX bank 0の96サンプル、1サンプル65535バイトまでです。STOP→PLAYと供給時刻を検査し、
符号化バイト列の完全一致でサンプルを共有します。保持はタイで記述します。
既定の `--pcm-policy strict` は既知の意味損失を伴う生成を止めます。
`best-effort`では発音開始時のpanを保持し、途中pan変更やmuteの損失を区間付きで診断します。
次の新規発音では元のpanを明示します。近似方法を定義できない入力はbest-effortでも生成を止めます。
ストリーム転送、不規則なbyte供給、再生途中の速度変更、decoder状態を引き継ぐ曲ループなどは
未対応として報告します。PCMを含む場合、長さ補正は共有OPM/PCM clockを保持して見送り、
その理由をnormalization JSONに記録します。PCMのstrict／best-effort判定は別途行います。

**PCMを含むMDXからのVGM生成は現在利用できません。** 外部ライブラリsoundlogの保持中カーソル消失と、
元VGMの再生状態を保持できない問題があるため、現在はMDX＋PDXまでを生成します。
バイト列・参照・タイミングの検査と、実機／エミュレータ上の音声確認は区別しています。
対応条件、中間結果、Z_MUSICに向けた分離は [PCM/PDX](docs/pcm_pdx.md) を参照してください。
`*.pcm.assessment.json`／CSVに、投影の `pass / lossy / unverified / fail`、既知損失、未確認事項、
成果物ごとの生成状態を保存します。strictによる停止でもレポートを残します。
投影がpassでも、独立環境での再生比較は `validation_status=unverified`、`validation_run=not_run` です。
型付き命令列は `*.pcm_target_commands.csv` と `<stem>.pcm/target.tsv` で確認できます。
標準MXDRVを独立基準にしたSegment比較の設計は
[PCM往復検証](docs/pcm_roundtrip_validation.md) に記録しています。この検証経路は未実装です。

### フォルダを一括出力する

[export_mdx.py](scripts/export_mdx.py)は、指定フォルダ以下の`.vgm`と`.vgz`を再帰的に処理します。
変換本体は`vgm2mml.py`、FMのMML→MDXはMXC、MDX→VGMはsoundlogを使います。

```bash
# PSG/SCC入力
python scripts/export_mdx.py tests/fixtures/public/psg \
  --outdir outputs/listen/psg

# ネイティブOPM入力
python scripts/export_mdx.py tests/fixtures/public/opm/from_mdx \
  --outdir outputs/listen/opm
```

入力は単一ファイルでも指定できます。入力と出力には別のフォルダを指定してください。
入力の相対パスを`tracks/`以下に保ち、曲ごとのフォルダ名には元の拡張子も残します。
同名の`.vgm`と`.vgz`は別フォルダになります。

```text
outputs/listen/psg/
  results.csv
  _compiler_inputs/
    volume_sweep/
      volume_sweep.vgm.mxc.mml
  tracks/
    volume_sweep/
      volume_sweep.vgm/
        volume_sweep.mdx.mml
        volume_sweep.mdx
        volume_sweep.vgm
        volume_sweep.conversion.json
        volume_sweep.mdx.normalization.json
```

成功曲のフォルダには3種類の成果物と経路・補正の診断JSONを生成します。MXCに渡したCP932／CRLFのMMLは
`_compiler_inputs/`に保存します。MXC用にタイの空白や長い休符などを調整しますが、
曲フォルダのUTF-8 MMLと元の中間表現は維持します。
MXC v1.01＋run68では、タイトルがCP932で65バイト以上になると空のタイトルが出力されることを確認しています。
この確認済みの条件だけタイトルを復元し、PDX名・オフセット・音楽データは同一のまま検査します。
`_compiler_inputs/`に元のMXC出力と`*.metadata.json`も保存し、復元の有無を記録します。
`results.csv`には各入力の成否、`compiler`、`compiler_input`と出力パスを記録し、
失敗時のログは`_errors/`に保存します。変換できない曲があっても残りを処理し、1件でも失敗した場合は
終了コード1を返します。途中まで生成できたMML/MDXは診断用に残ります。
再実行では同じ曲の既存3ファイルを置き換えます。

PCMにも `--pcm-policy strict|best-effort` を渡せます（既定strict）。
PCMを含む入力は既存の型付きMDX＋PDX生成を使用し、FM部分のコンパイルはmmlxです。
この経路は`compiler=typed_pcm_mmlx`と記録します。`--compiler`の選択はFMのみの入力に適用します。
生成できた場合はMML＋MDX＋PDXを保存し、`results.csv`に
`pcm_replay_unavailable`と記録して終了コード1を返します。PCMのVGM欄は空です。
strictで既知損失を拒否した場合は `pcm_projection_blocked` となります。
`pcm_projection_status`、`pcm_validation_status`、`pcm_validation_run`、`pcm_known_losses`、
`pcm_assessment`を別の列に記録します。PCMのbinding／projection CSV、命令列、評価レポートとpacking用サンプルも診断用に残ります。
再実行では以前のPDXとVGMを削除してから処理するため、古い成果物を成功結果として扱いません。

再生tick上限は実際のVGMの待ち時間から自動計算します。`--max-ticks N`で指定することもできます。
`--generator PATH`で検査・再生helperを、`--timeout N`で各処理の制限秒数を指定できます（既定180秒）。
`--psg-model`、`--psg-gain`、`--scc-gain`、`--opm-pitch-policy`は変換本体へ渡します。
`--normalize-lengths`／`--no-normalize-lengths`も渡せます。省略時は通常変換と同じ既定値です。
PCM helper／policyの設定はPCMがない入力には適用せず、その非適用もconversion JSONに記録します。
PSGのノイズ・ハードウェアEGなどの未対応動作は、一括出力でも失敗として記録されます。

## 検証

```bash
python -m unittest discover -s tests/scripts -v
```

WAV解析のテストにはNumPyが必要です。外部MDXコンパイラを使う検証は別途実行します。
公開データでの生成・コンパイル確認に加えて、以下の往復検証を維持します。
MML生成処理の確からしさを、戻したOPMの状態・Segment・Keyイベント・時刻から検査します。
往復検証の成功と、MXDRV／MMDSP上の表示・再生確認は別の結果として扱います。

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm --outdir outputs/opm/roundtrip
```

往復検証は [外部fixture generator](scripts/mdx_fixture_generator/README.md) を利用します。
`verify_opm_mdx_roundtrip.py`でも、MML → MDXは既定で **MXC**、MDX → VGMは
**soundlog 0.15.0** を使います。`--mxc`／`--run68`でツールの場所を指定でき、
`--compiler mmlx`で従来のコンパイラを明示選択できます。比較処理は同じです。
コンパイラ初期化データも選択したコンパイラで生成し、結果に`compiler`と
`compiler_input`を記録します。MXCに渡すMMLも検証フォルダに残します。
長さ補正は通常変換と同じ既定値で、`--no-normalize-lengths`で無効化できます。
経路は `VGM → Segment → MML → MDX（MXC）→ VGM（soundlog）→ Segment` です。
mdxtoolsの `mdx2mml` は既存MDXから独立した参照MMLを作るために、`mdxdump` は構造・メタデータ確認に使います。
fixtureは既存の `tests/fixtures/public` と `tests/fixtures/local_only` に置き、構造を維持します。
非公開fixtureと生成物はGit管理対象外です。

生成VGMと別ツールのOPM VGMをSegment単位で調べるには、次を使えます。
チャンネル番号は0始まりで、左の入力から右の入力への対応を明示します。

```bash
python scripts/compare_opm_vgm.py generated.vgm comparison.vgm \
  --channel-map 5:4,6:5,7:6 --outdir outputs/compare
```

`report.json`に状態・Keyイベント・終端・待ち命令の集計を、CSVに両入力の
Raw／State／Segmentと比較区間を保存します。比較範囲は短い方の終端までです。
未観測値を未知のまま扱い、休止中の状態や同一時刻のKeyイベントも残します。
対応は入力ごとに確認してください。上の対応は今回確認したPSG出力とvgm-conv出力の例です。
この診断は波形一致やループ継ぎ目、MMDSPの表示動作を保証するものではありません。
Key命令の前後の瞬間的な状態・書き込み順序は、別の厳密な往復検証で確認します。

## 構成

- `vgm2mml.py`：通常変換の入口。
- `py/opm_conversion.py`：OPM入力からMDXへの変換手順。
- `py/psg_scc_conversion.py`：PSG/SCC入力からOPM MDXへの変換手順。
- `py/`：チップ解析・中間表現・ターゲット生成。
- [scripts](scripts/README.md)：一括出力、診断、往復検証、fixture生成、比較用ツール。
- [設計原則](docs/project_knowledge.md)。

## 謝辞

本プロジェクトのMDX/VGM出力と往復検証では、以下のツールを利用しています。開発者・メンテナー・貢献者の皆様に感謝します。

| プロジェクト | 本リポジトリでの用途 |
|---|---|
| MXC v1.01（MFS soft, milk、[MDX_TOOL.lzh](https://nfggames.com/X68000/Mirrors/x68pub/x68tools/SOUND/MXDRV/MDX_TOOL.lzh)）と[run68x](https://github.com/kg68k/run68x) | FMの聴き比べ用出力とOPM往復検証で、既定のMML → MDXコンパイルとHuman68kプログラムの実行に使用。 |
| [mmlx](https://github.com/h1romas4/chipstream/tree/main/crates/mmlx)（h1romas4/chipstream） | 明示選択したMML → MDXコンパイル、既存の開発用診断・公開fixture生成、PCMを含む生成のFM部分で使用。 |
| [soundlog](https://github.com/h1romas4/chipstream/tree/main/crates/soundlog)（h1romas4/chipstream） | FMのMDX → VGM変換、PDX構築・PCM参照検査。PCMのVGM再生には現在制約があります。 |

外部コンパイラ・再生ツールはMDX/VGM出力や開発・検証用の任意依存です。
OPMのみのVGM → MML変換はPython側の実装で行い、PCMを含む通常変換はPDX packingにもhelperを使用します。

