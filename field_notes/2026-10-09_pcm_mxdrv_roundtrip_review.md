# 2026-10-09: PCM再生意味論、独立基準、A/B/C往復検証

## 依頼と現在の結論

ユーザーの目標は `VGM -> PCM IR -> MDX+PDX -> VGM`。
PCMのMMLテキストは必須要件から外し、OPMは既存の音楽的MDX生成経路を利用する。
今回の作業は調査と検証設計の保存であり、PCM直接MDX出力や往復比較器は実装していない。
検証設計は [docs/pcm_roundtrip_validation.md](../docs/pcm_roundtrip_validation.md)。

問題をMML/compiler、target MDX実行環境の表現可能性、MDX+PDX replay converterに分ける。
tie→F7、pan→FC、F→EDはMDX命令として残る。MMLを省略して全問題が消えるとは言えない。
soundlog raw cursorの消失はcompilerではなくMDX replayの不具合。
一方、保持中pan/Fが標準driverで適用されない場合は、target投影の問題として診断する。

前回の「nativeでは各音符で物理decoder resetするのに再生器が省略する」という断定は強すぎた。
正確には、元VGMのreset関係を現行再生器が保持できず、標準MXDRV+IOCSの物理制御との一致も未確認。
note、IOCS開始/終了、DMA終了、チップSTOP/PLAY、decoder resetを同一視しない。

## soundlog 0.15.0の再確認

ローカルCargo source `soundlog-0.15.0/src/mdx/convert.rs`を読んだ。
crate VCS情報は`h1romas4/chipstream` commit `7e0c97733d3636e40ee23233c898e74691d48417`。

- 1728–1732: LegacyAdpcm track8でnon-Note命令を読むたびraw sample/cursorをclear。
- 1618–1621: heldな同じblockの次Noteはearly returnし、raw sampleを再設定しない。
- 1591–1594: logical keyoffはchannel/hold処理で、物理チップ制御と同一ではない。

interior F7やcontrolで供給cursorを失う問題を、MML記法の問題とは扱わない。
cursor clearだけを削除すると、停止後の供給やresetを別途扱う必要が残る。
standard profileの規則を確認してから限定修正する。

## ネイティブMXDRV 2.06+17 Rel.X5-Sの根拠

`assets/`の関連資料を検索した範囲では、MXDRV/IOCS一次資料は見つからなかった。
追加web調査で`vampirefrog/x68kd11s`のネイティブバイナリ逆アセンブルを発見した。
対象ファイルの最終変更commitをAPIで確認し、公開ソースのみ固定commitで保存した。

- commit: `19a79218a4fbe0651371bd2f2d909a92897c8e52`
- path: `sound/mxdrv/2.06+17_Rel.X5-S/mxdrv17.s`
- [固定source](https://github.com/vampirefrog/x68kd11s/blob/19a79218a4fbe0651371bd2f2d909a92897c8e52/sound/mxdrv/2.06%2B17_Rel.X5-S/mxdrv17.s)
- 保存: `outputs/research/x68kd11s/mxdrv17.s`, `provenance.json`。sourceはcp932。
- headerは`mxdrv17.x`からのDIS 3.16逆アセンブルであることを記録。

ラベル名の一部は解析者由来。正式author sourceやROM IOCS実装と同一視しない。
以下は通常PCM1/IOCS branchに限定したコード根拠である。

| 処理 | 元source行 | 読み取れること |
|---|---|---|
| F7 | 2043–2045、1839–1846 | track flag 0x04を立て、gate keyoff countdownを抑制 |
| PCM note要求 | 1518–1523 | active flagが既に立つとsample lookupより前にreturn。same/different sampleの比較で決める処理ではない |
| FC pan | 1991–2001 | PCM trackの状態に保存しreturn。ここではIOCS/PPIへ即時出力しない |
| ED rate | 2211–2215 | PCM trackのrate bitsへ保存しreturn。新規ADPCMOUTのmodeへ持ち越す |
| 新規PCM1開始 | 1535–1575 | PDX範囲を選び、ADPCMMOD(0)の後、mode/byte count/addressを渡してADPCMOUT |
| PCM gate keyoff | 1678–1688 | 条件付きADPCMMOD(1)、その後ADPCMMOD(0)。中断と終了を区別 |
| gate/休符 | 1842–1879 | gateとnote durationを別カウンタで処理。休符は次イベントとして解釈される |
| PCM1 sample length | 1561–1574 | PDX entryのlength上位wordを飛ばし、末尾wordをzero-extendしてbyte countへ渡す |

この版の通常FC/EDは、新しいIOCS sample開始へlatchされる。
保持中FCをtieで挟む現行出力は、元VGMの即時panを再現するものとして認証できない。
またPDX container/packerが24-bit lengthを格納できても、このnative PCM1での再生能力とは別。
sample length境界を今後検証し、target eligibilityへ反映する必要がある。
現行bank0の短いpublic sampleにはこのlength境界を検証する材料がない。

ここから確定できるC1はdriverの要求層まで。
IOCSが実際にどのチップ制御/データをいつ書くか、decoderをどうresetするかは、
ROM IOCSの特定版のコードまたは独立した実行traceが必要。
今回ネイティブMXDRV/IOCSを実行したわけではない。

## NanoDrive8: 標準とは区別する

commit `3559c88f845a5a6b685520b86b8cb91409b3f4c9`を調査。
[固定source](https://github.com/Fujix1/NanoDrive8/tree/3559c88f845a5a6b685520b86b8cb91409b3f4c9)。
保存資料は`outputs/research/NanoDrive8/`。ESP32-S3から実音源を駆動するfirmwareで、
確認したVGM経路は入力parser。MDX+PDX→VGM writerやWSL用headless CLIは確認していない。

- `src/mdx.cpp:1211`以降のstop helperはblock/cursor/holdをまとめて解除。
- `:1438`, `:1457`, `:1534`はrest、F7、同一block保持の処理を分ける。
- `:1576`はnew attackでpanを適用。FC handler `:1691`以降はtrack state更新。
- `:1372`の物理STOP、`:1545`のnote時PLAYはコメントアウト。
- `src/okim6258.cpp:789`以降はraw PDX供給cursorを保持し、末尾を自動rewindしない。
  無データ時の0x80供給はこのfirmwareの挙動であり、汎用silence/reset規則ではない。
- `src/vgm.cpp:1460`以降のdirect B7制御とMDX経路は別である。
- NDSIFはhost→device APIであり、標準IOCSのoracleやVGM recorderではない。

cursor寿命・logical stop・held EOF設計の参考にはなるが、標準MXDRVの物理制御の代用にはしない。
標準driverとの違いを別profileとして比較する。
`src/mdx.cpp`/`include/mdx.h`はREADMEの一律BSD-3対象から除かれ、由来ごとの条件がある。
今回コードの取り込みやfirmware build/実機検証は行っていない。

## 別のMDX→VGM実装を実測した結果

`LeonardoDemartino/mdx2vgm` commit `00e00ff767ee52c941987fd586c78d021349a99`。
[固定source](https://github.com/LeonardoDemartino/mdx2vgm/tree/00e00ff767ee52c941987fd586c78d021349a99)。
前回WSLで未改変sourceをbuildし、publicの2組MDX+PDXを実行した。どちらもexit0でVGMを生成した。
結果は`outputs/research/mdx2vgm/{experiment_summary.md,metadata_summary.json,cases/}`。

- PDX slot0の符号化payloadは完全一致。
- F0/F4を含むケースでもstream write frequencyはどちらも7813に固定。
- panは0固定、stream STOP/チップSTOP出力なし。
- `src/mxdrvg_core.h:482–500`の固定出力と`:548–558`のADPCMMOD STOP/END stubが裏付ける。
- sparse PDXのslotとdense block IDの対応も要確認。slot0のみの実測では未再現。
- clockは正しいheader offset0x90の8MHz。0x98はOKIM6295なので拒否理由にしない。
- options0x06のbit2は4-bit想定との整合を要確認。VGM spec自身もこの切替の未対応を記載。

正常終了やpayload保存だけで、PCM replayのoracleとしては採用できない。
mdxtools commit `9c8539fec2757fcf7c85d1986171b50ebe2ef1e5`も確認。
mdx2vgmは標準PROGSに入らず、mdxplayのVGM loggerはFM側への接続。
WAV経路やportable_mdx/X68Soundは補助候補だが、この調査でbuild/音声検証はしていない。

## 実行profileが必要な理由

[XAPNEL](https://github.com/kg68k/xapnel-src/tree/4e60938a3d963ed5148a559336ff200cb4177dbb)
は標準IOCSのADPCM出力関連を差し替える実装。
READMEは機種差への対応、安定化データ長の変更、中断/復帰の修正を記録し、
Z-MUSICに同等コードが組み込まれ、PCM8とは制御経路が異なることを説明する。
これは標準挙動の根拠そのものではなく、IOCS/常駐driver差が実在する根拠である。
基準RはMXDRV版に加えROM IOCS版・機種・差替え有無を固定する。
Z_MUSICの再生profileを標準MXDRVへ混ぜない。

[VGM specification](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/vgmspec171.txt)
では0x90–95はデータ書込みschedulerの制御。stream stopとチップSTOPは別。
[MAME OKIM6258](https://github.com/mamedev/mame/blob/master/src/devices/sound/okim6258.cpp)
もchip状態の参考だが、modelの版を記録し、実機specの代わりに一般化しない。
今回の短い探索でSharp純正IOCS原本/ROM実装の特定まではできていない。

## 決めた検証方針と次の作業

- A/BのOPM/PCM意味論比較を採用。raw command列は診断用に残す。
- Rは独立したnative MXDRV+IOCS環境。生成MDXもRで再生してB_refを最初から取る。
- C0は元MDX+PDXの直接解析、C1は版付きdriver/IOCS規則による実効再生情報。
  F7/q等の原コマンド配置はVGMから一意復元不能なのでA/Bの必須一致にしない。
- C1/A、A/B_ref、B_ref/Bを個別比較。許容差付き一致を推移的に扱わない。
- 供給と消費、full assetとplayed prefix、note/cursor/reset、要求と実効pan/rateを分ける。
- source時刻、MDX投影誤差、R/Pの時間丸めは別予算。6sample許容をresetや供給間隔に流用しない。
- 不明項目はunverified。sample bytesやstatic参照の一致をPCM往復成功とは呼ばない。

次はRのprofile/観測手段を用意し、自作短いMDX+PDXで規則を確かめる。
途中panのtarget loss判定とnative sample length境界を先に判断し、その後source stream/消費モデル、
PCM直接MDX出力とP修正へ進む。新しい汎用compiler/decoder/playerを一括実装しない。
PCM検証CLIは未実装である。

## ユーザー追加方針: strict / best-effort

検証方針は合意済み。ただし、targetで完全に再現できない入力を一律にrejectしないことが追加された。
実用成果物の生成と厳密な往復成功を分ける。

- strict: 既知lossを伴う投影を出力しない。
- best-effort: 明示選択した定義済み近似に限り、loss診断とともにMDX+PDXを生成できる。
- pass / lossy(known loss) / unverified / failをscope付きで分ける。
  target仕様上の損失とIOCS未確認を混同せず、再生不具合を既知lossへ格下げしない。
- 元PCM IRは変更しない。target profile、fallback、source ID/time/影響区間、
  元値/projected値、loss理由/証拠と未確認事項をMDX projection/report側に保持する。
- artifact generated/blocked/errorは意味論判定と別。lossとunknownがあれば両方を表示する。
  必須項目が未確認なら総合unverified、予想外の不一致があればfail。lossyは厳密往復成功ではない。
- strictは既知loss禁止であり、runtime認証済みを意味しない。
  整合したtarget planを生成できるがIOCS未確認の場合、成果物とunverified診断を残せる。
  planを定められないsource未解釈等はbest-effortでも生成保留できる。
- 途中panの近似候補は発音開始時panの保持と途中変更の不適用。
  次の新規発音にはその時点のsource panを使い、人工的なretriggerは追加しない。
  muteの欠落が可聴性を変える場合も影響区間として記録する。
- A/B_refの既知lossは報告し、選択した近似の実現を別途検証する。
  B_ref/Bは同じ生成MDXの比較なので、sourceからのlossを再生器差の言い訳にしない。

この追記は設計の更新。新しいCLI mode/reportは未実装で、既存converterの拒否条件は変更していない。
次のeligibility実装では、loss診断とstrict/best-effortの選択を同時に用意し、
忠実性の不足を示すだけで実用出力の選択肢を一律に閉じない。

同日の後続実装で、policy切替・評価レポート・型付きPCM直接MDX生成を追加した。
上記は調査時点の記録。現状と検証結果は
[target projection実装記録](2026-10-09_pcm_target_projection.md)を参照する。
