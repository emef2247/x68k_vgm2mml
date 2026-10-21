# OPMクロックとMDXの音程補正

MDXの再生先はX68000の4,000,000Hz YM2151です。入力VGMが異なる
YM2151の正のクロックを宣言していても、単一インスタンスならTargetで補正します。
Raw、State、Segmentのクロック、時刻、KC/KFは変更しません。

## 補正の位置と計算

`opm_mdx.project_segments`が共通の入り口です。structured／legacyの音符、
registers（channel／conductor）のレジスタ、PCM併用のFM部も同じ投影を使います。
PSG／SCCのOPM投影は既に4MHzを生成するため追加の音程変更はありません。
`--no-normalize-lengths`でも音程補正は有効です。時間の正規化とは別の処理です。

```text
pitch offset in 1/64-semitone units = round(768 * log2(source clock / 4,000,000))
target pitch = source KC/KF pitch + offset
```

KCの穴・別名とKFの上位6bitを使って音程位置を計算します。入力クロックが
低い場合は出力KC/KFを下げ、再生先クロックによる音程上昇を相殺します。
3,579,580Hzでは補正は-123/64半音です。KCのみ／KFのみの変更にも対応し、
繰り上がりが必要なら同じsource eventから両レジスタを出力します。
各命令は`target_sequence`で順序を保持します。4MHz入力の命令値は変更しません。

範囲内の計算は公称の対数音程に基づき、丸め誤差は最大0.78125 centsです。
範囲外のclampは別の損失で、誤差がこの値を超える場合があります。
実チップの周波数ROMや演奏音を測定して同一性を確認した値ではありません。
参照したKC/KF索引とクロック比例の実装は
[mdxtoolsのYM2151実装](https://github.com/vampirefrog/mdxtools/blob/master/ym2151.c)
です。ROM表やエミュレータコードは取り込まず、対数式を独立に実装しています。

## 未知の初期値と範囲外

- 異なるクロックの入力に限り、未書き込みKC/KFを出力側のreset-zero仮定として
  扱います。元のStateの`None`は保持します。最初の発音に必要なKC/KFは両方とも
  Key-On前に設定し、MXDRVの既存値には依存しません。
- 通常KCの96音域と最上端KC `0x7f`の別名を扱います。
  KCのbit7、KFの下位2bitは音程に使用せず、元のbyteはCSVに残します。
- 既定の`--opm-pitch-policy clamp`は範囲外を最寄りのKC/KFへ寄せます。
  音程差、件数、source eventを損失として記録します。3,579,580HzのKC/KF=0では
  下限へのclampに約+192.252 centsの差があります。
- `--opm-pitch-policy error`は厳密な範囲検査を維持します。初回Key-On前の
  範囲外セットアップは保留できますが、発音までに解決しない場合、
  または初回発音後（リリースを含む）の更新はエラーです。
- この範囲はKC/KFレジスタの指定範囲です。Segmentに独自の許容枠を設定したもの
  ではなく、音色側の倍率なども変更するHW全体の実現可能性を判定していません。

## 検査できるデータ

`--dump-passes`で次を保存します。

- `.opm.segments.csv`：変更しない入力Segment。
- `.mdx.pitch.csv`：source event／Segment、入力クロックと元KC/KF、
  未書き込み値の仮定、出力KC/KF、公称音程誤差、clamp／保留した初期化。
- `.mdx.controls.csv`：`register,data`は出力命令、`source_register,source_data`は
  元の命令。追加のKC/KFも元のsource eventへたどれます。
- `.mdx.timing.json`と`.mdx.normalization.json`の`pitch_projection`：補正の概要。

TXTでは`OPM clock and pitch projection`を確認してください。
`Pitch range policy`のclamped eventsは音符数ではなく、音程更新／Key-On評価の件数です。
通常の丸め誤差とclampによる誤差を別々に表示します。
仮定の件数は影響を受けたイベント数であり、チャンネル数ではありません。
roundtrip比較は補正後の期待値との一致を確認します。
KC/KFの対は同一source eventの最後まで反映してから比較します。

## 補正の限界

DT1のHz単位のdetune、EGとkey scaling、LFO、ノイズ、チップタイマーは
再調整しません。音程レジスタが一致しても音色・変調・リリースまで
音響的に等価とは限りません。PCMのrate／符号化バイトは変更しません。
dual-chip／別チップ種は引き続き対象外です。


## Protected interval tick allocation

音程補正とは別に、`py/opm_output_normalization.py`は時間の正規化時に
共有FM/PCMクロックへ境界を割り当てます。2026-10-11に導入された方式は、
現在は共有ヘルパー`py/ordered_timing.py`の`allocate_tick_domains`を使います。
ソースのState、Segment、PCM IRや元の時刻は変更しません。

- 最寄りtickへの丸めで、保護対象の正の区間が潰れた場合だけ、同じ絶対境界
  移動許容量内で順序付き割り当てを試します。許容量は
  `floor(44100 * --normalization-ms / 1000)` source samplesで、既定は352です。
- 各境界に、投影後の整数source-sample時刻が許容量内になる厳密な整数tick領域を
  与えます。MDXラッパーは原点0をtick 0に固定します。隣接境界は非減少、
  protected intervalの終端は始端より少なくとも1 tick後、という辺からなるDAGを
  解きます。途中の通常制御境界が同じtickにまとまることは許されます。
- 保護するのは曲全体、残存FMゲート、保持中の部分Key操作・再発音の区間、
  許容量を超える休符、正の副作用パルス、残存PCMゲート、許容量を超えるPCM休符、
  有効な曲ループ区間です。完了していない終端ゲートも残存ゲートです。
  短いSegmentや未完了ゲートを、完結した短音として省略してはいけません。
- 領域内に解がなければヘルパーは`None`を返し、その候補を不採用にします。
  不正な入力配列・区間参照は`ValueError`です。割り当て後にも境界誤差、原点、
  全体の順序、保護区間の正の長さを独立に再検査します。許容量を緩めて
  強制採用したり、黙ってループや発音を落としたりはしません。
- 他の候補も成立しなければ、元のstructured投影と共有クロックへ戻ります。
  候補側の短音省略も採用しません。PCMの候補固有の失敗と、ソース自体の
  eligibilityエラーは別です。後者が正規化で解消したことにはしません。

採用した`boundary_ticks`は投影に格納し、FM、PCM、validator、pass dumpが
同じ対応表を使います。`.mdx.normalization.json`は`boundary_allocation`、
`adjusted_nearest_boundaries`、protected intervalや棄却候補を記録し、
`.mdx.normalization.csv`で元時刻・候補tick・誤差を追跡できます。
短音省略と候補選択の詳細は[音価と正規化](opm_note_lengths.md)を参照してください。

## 実装確認と履歴の範囲

この文書のKC/KF補正・pitch policyは`py/opm_pitch_projection.py`、時間割り当ては
`py/opm_output_normalization.py`と`py/ordered_timing.py`の現行コードと照合しています。
既存の`tests/scripts/test_opm_pitch_projection.py`は全notation/layout、未知初期値、
clamp/error、リリース後の範囲外更新、source保持、ペア書き込みの検証を含みます。
`tests/scripts/test_ordered_timing.py`は実現可能・不可能な制約、非隣接区間、原点を含む
固定anchor、入力非変更、厳密なMDX領域を扱います。今回これらのテストは読取のみで、
再実行していません。

2026-10-11当時のrange-errorのみの方針は、現在の既定clampに先行する判断です。
実装時の検証結果・私有曲の視聴・試行履歴は、外部ノート
`field_notes/2026-10-11_opm_clock_projection.md`に残します。
そこでの成功件数や視聴結果を、現在のコードや全ドライバの検証済み仕様とは扱いません。
