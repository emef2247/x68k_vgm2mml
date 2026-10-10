# PCMのオフセット・PDX構造・有限終了の照合

作業停止：ユーザーは実装前に方針を検討したいと指定した。PCM8出力は検討可能と
されたが、実装・比較用MDX/PDX生成は未着手。追加のdata-profile reviewも中断した。
再開の依頼があるまで調査・実装を進めない。停止不良の原因は未特定のまま。

その後、ユーザーは提供した参照MML/MDX/PDXがXM6 TypeGで正常に再生・終了する
ことを明言し、再生画面も提示した。この動作確認済みの参照を出力構成の基準とする。
PCM1/PCM8の区分は対応する生成形式を内部で選ぶための情報であり、参照に従う
作業を妨げる理由や、追加の環境確認を要求する理由にしない。現在のdefault PCM1
に参照を無理に限定せず、参照側の適用可能な構成・発音／保持／終了記述に合わせた
targetとtool入力を検討する。source PCM IRへtarget都合の制約を戻さない。
これはユーザーによる実再生観察の記録であり、全再生意味論の自動認証とは別である。
実装停止は維持し、この訂正時点で新たな生成処理や比較データは作っていない。

最新のユーザーによる範囲訂正：目的は忠実で正しいMDX/PDXデータの生成である。
外部移植ツールの未実装を修正する作業や、再生環境の追加調査は今回の対象ではない。
以下のruntime切り分け案は過去の提案として残すが、次の作業指示とは扱わない。
生成物のoffset、length、sample bytes、PCM音符長、保持解除、終端を仕様と参照
データに照合する。環境回答をデータ生成作業の前提にしない。

ユーザーはBOSCON06の演奏自体は良好だが、終端でノイズが入り、止まらない場合が
あると報告した。今回の範囲は、整理済みの参照MML/MDX/PDXとの静的比較と、
ドライバ由来コードによる終了要求の追跡。productionの生成処理、source timing、
sample bytes、XM6設定は変更していない。停止問題の解決／実音声停止は未確認。

## 参照集合と検査範囲

現在の集合は15 MDX、8 PDX。原MMLはFF4SIRENとRAY2Cの2件。
FF4SIRENは標準9track PCM1で、P trackはループ終端。残る14 MDXは16trackの
PCM8拡張である。113 PCM trackの符号化末尾を調べると、音符を含む有限終了trackは
18本あったが、すべてPCM8側だった。標準PCM1の有限終了を実再生で保証する
参照曲は、今回の集合からは得られていない。

PDX tableの範囲は最小の非空sample offsetから推定した。これは構造上の検査境界で
あり、PCM8 driverのbank選択を実行した結果ではない。MDXのFD bankとNOTEは
符号化順に照合したが、repeat/escapeを実行する完全なC1ではない。
7個のNOTE参照は空slotを指していた。空slotは意図的な無出力にも使えるので、
これを原曲の不正参照や再生失敗と断定しない。

## オフセットを区別する

| 値 | 基準と意味 | MMLとの関係 |
|---|---|---|
| MDX headerのtrack/tone offset | MDX data baseからの16-bit位置 | compiler/builderが配置する。MML文字数や各track長そのものではない |
| MDX repeat/song-loop operand | 命令が定義する相対位置 | `[...]`、`/`、`L`から生成される。PDX addressとは別 |
| PDX sample offset | PDX table baseからの32-bit byte位置 | P trackのNOTEはsample番号を選択する |
| PDX sample length | sampleに渡すbyte数 | 標準PCM1はlengthの下位16bitを使用する |

標準PDXの1 entryはoffset long、zero word、length wordで、96 entryが768 bytes。
EX-PDXではlength側もlongとして使える。
[当時のMXDRV内部資料の転載](https://w.atwiki.jp/mxdrv/pages/23.html)と、ローカルの
MXDRV2.06+17 Rel.X5-S逆アセンブルを照合した。標準PCM1のsample取得は
`adda.l`でoffset全体を加算し、length上位wordをskipして下位wordを読む。
したがってPDX全体のサイズ／sample位置が65535を超えることと、1 sampleの長さが
65535を超えることは別の問題である。

[MXC付属MML資料の抜粋](https://w.atwiki.jp/mxdrv/pages/19.html)にはsample途中の
byte offsetを直接指定する標準構文は見つからなかった。Pの通常音符／`n`はsample
番号を選ぶ。必要ならsample sliceの配置はtarget PDX側で考えるが、decoderの
continuation/resetを保てることは別途検証が必要。今回はsliceを追加していない。
`!`はcompile時に以降を無視する指定で、PCMのruntime STOP命令ではない。
有限repeatは符号化サイズを減らせるが、別のaddress domainの上限やPCM停止を
解決する根拠にはならない。

## PDX構造の結果

| PDX | file bytes | 非空samples | 最大sample bytes | offset >65535のsamples |
|---|---:|---:|---:|---:|
| FF4SIREN | 2221 | 1 | 1453 | 0 |
| SFA02 | 120914 | 26 | 17540 | 3 |
| SFA02_ | 121880 | 26 | 17510 | 3 |
| SFA11 | 25708 | 13 | 6096 | 0 |
| RAY01C | 840134 | 156 | 12000 | 141 |
| RAY2C | 319068 | 48 | 14000 | 31 |
| RAYFOR | 187296 | 28 | 15643 | 16 |
| RF2 | 16465 | 9 | 4223 | 0 |
| generated BOSCON06 | 71941 | 55 | 3196 | 7 |
| generated BOSCON07 | 52859 | 24 | 3406 | 0 |

全10 PDXで非空entryのoffset/lengthがtable外のfile内を指し、範囲外アクセスに
なるentryはなかった。全sample長は65535以下。奇数offsetと奇数lengthは原PDXにも
存在し、生成物だけの異常ではない。全fileで最後のsample範囲がfile末尾に達して
おり、sample外の末尾paddingはなかった。

BOSCON06の最後はbank0 slot54、offset71574、length367で、
`71574 + 367 = 71941`、PDX file末尾と一致する。PDX addressの16bitへの切捨てや
sample長の巻戻りを示す不具合は今回の静的検査で見つかっていない。
標準PDXはtableの長さで再生範囲を渡す。ADPCM payloadの末尾に停止opcodeを
足す形式と解釈しない。sample外paddingや無音bytesの追加は行わない。
この検査は構造／binding検査であり、decoder消費や実音声の等価性は証明しない。

## 末尾のPCM停止要求

原FF4SIRENのPはF4、rest、NOTE、finite repeat、Lを使い、無限ループへ戻る。
原RAY2CもPCM8のloop参照である。PCM8の有限終了例にはrestを挟むtrackと
NOTE直後にF1/00へ進むtrackの両方があり、一部にはF7保持もある。
これらから「有限終了には必ず最後のrestが必要」とは導けない。

生成BOSCON06の最後のplayback139はsource samples1180591..1182662。
`termination=source_end`であり、観測されたchip STOPではない。記録終了までPLAYが
activeなことと、targetが有限演奏として閉じることを区別する。367 bytesから計算
する公称sample長と184 MDX ticksの音符長も完全に同一ではなく、実際のdecoder
消費数は不明のままである。終端の短い音の差と、終了後も続く音を混同しない。

target末尾はstart104573、end104757、F4、pan3、q8、NOTE slot54/184 ticks、
F1/00。最後のNOTEにF7保持はなく、後続restもない。
調べた+17標準PCM1では、q gate expiryを処理してからnote duration expiryを
処理する。encoded durationはN-1で、q8のgateは`(N-1)*8/8 + 1 = N`。
q8が音符長より1tick遅れるという計算は誤りである。

Key-Offは標準PCM1のIOCS `_ADPCMMOD`（trap15、D0=0x67）に進み、D1=0の
終了要求を行う。状態によって先にD1=1の一時停止要求も行う。F1/00の全track終了
自体には標準PCM1を無条件に切る独立処理はない。PCM8有効時のtrap2/0x01ffは
拡張側の処理なので、これを標準IOCS停止と説明しない。

独立したmdx2vgm移植コードrevision
`00e00ff767ee52c941987fd586c78d021349a99`の診断copyで、200000 ticksのhard bound、
20秒timeoutを設定して生成BOSCON06を実行した。最後のADPCMOUTはtick104573、
length367。tick104757でADPCMMOD_ENDを呼び、tick104758で全track終了、active mask0、
fatal0となった。停止要求とsequence終了のintentは確認できた。
STOP/ENDは空stubなので、IOCS/DMA/ADPCMの実停止を証明する試験ではない。
portが出したVGMをPCM oracleとして比較に使っていない。

ユーザーの指摘により説明を訂正：空stubは外部の検証用移植ツール側の未実装であり、
再生環境の差を理由に正当化するものではない。このツールはMMDSPの再生経路に
関与せず、BOSCON06の停止不良の原因とも断定できない。生成MDXの停止条件は
参照MXDRVを基準に満たすべきで、PDXを個別環境へ適応させる問題ではない。
移植ツールを停止検証に使うには、参照の終了・中断要求を実際に処理するbackendが
必要。停止要求の呼出しログだけを実装完了や停止保証として扱わない。

## 残る切り分けと再開条件

### 最新：MML／PCM IR／MXC出力の静的な受け渡し比較

ユーザーの範囲訂正後、生成06/07のPトラックMMLを抜き出し、共通tempoを付けて
MXC v1.01でPCM-only MDXへコンパイルした。PCM音声を再生するツールは使用して
いない。独立した既存mdxtools command inspectorで生成MDXとMXC出力を読み、
finite repeatを展開したNOTE/F7の順序・sample番号・音符長を比較した。
両曲ともNOTE/F7全列が一致した。06の最後は184ticksで保持なし、その次がF1/00。
07も最後の音符に保持がなくF1/00で終わる。06の終了情報がMMLとtyped PCM入力／
MDXとの間で脱落した形跡は、この静的比較では得られなかった。

直接のMXC投入はタイ前の空白により失敗した。`prepare_mxc`はA-Hだけを対象とし、
Pには既存の空白／改行タイ調整を行っていない。失敗logを保存し、診断用copyに
同じ構文調整を適用して再コンパイルした。sample番号、音符長、保持の意味は変更
していない。canonical MML／production adapterは未変更。このcompatibility gapは
記録するが、現在のPCM MDXはtyped planを使うので、MMDSP停止不良の原因としない。
全control列がbyte一致するという主張でもなく、不要な同値設定の省略等は異なる。
音符／保持／末尾の比較は成功したが、PCMが実際に止まることの保証とは別であり、
ユーザー報告の原因は未特定のまま。

Evidence: `outputs/pcm_stream_2026-10-09/end_reference_review/mxc_handoff/`
のsummary.json、native MDX、prepared MML、encoded command CSV、失敗log。
診断scriptは`outputs/pcm_stream_2026-10-09/audit_pcm_mxc_handoff.py`。
private/generated内容はignoredに保持し、stageしない。

### 以下は現在の対象外となったruntime調査案

今回の画像はDRIVER MADRVだが、NOW PLAYINGはDSLY4_03である。BOSCON06の
実再生driverをこの画像から確定しない。以前のMXDRV30.x/PCM8報告も、今回の
BOSCON06の再生経路の証明とは別。BOSCON06固有のdriverと、終了表示後にも音が
残るのか／演奏時間が続くのかをユーザーに確認中。

次は実際に読み込んだMDX/PDXのhash、解決したPDX pathとdriverを固定したうえで、
最後のsample address/length、IOCS呼出しと戻り値、DMA状態、ADPCM control、終了
前後の音声を追跡する。停止要求が実行されない、DMAが止まらない、停止後も出力が
残る、を分ける必要がある。原因が確定する前にrest、F7、sample paddingを追加して
症状を隠さない。ユーザー観察を既知の許容lossとして処理しない。

独立レビューも、静的なPDX address／最後のNOTE encodingの欠陥は示されておらず、
runtime未解決を保ち実再生経路のtraceへ進むという結論を確認した。
production変更がないため今回の検証はread-only監査とbounded intent probeであり、
前の実装checkpointのunittest結果を今回の停止保証として流用していない。

Ignored evidence:

- `outputs/pcm_stream_2026-10-09/audit_end_references.py`
- `outputs/pcm_stream_2026-10-09/end_reference_review/summary.json`と各PDX table CSV
- 同folderの原MML PCM抜粋（private内容を含み、commitしない）
- `outputs/pcm_stream_2026-10-09/probe_boscon06_end.py`
- `outputs/pcm_stream_2026-10-09/end_reference_review/intent_probe/summary.json`、
  stdout/stderr、terminal_states.csv、build/configure logs
- `outputs/research/x68kd11s/mxdrv17.utf8.txt`のsample取得、SendKeyOff、gate、EndPlay
  （tool/source素材はignoredのまま）
- 過去の小fixtureのintent probeは
  `field_notes/2026-10-09_mmdsp_pcm_stop_observation.md`を参照
