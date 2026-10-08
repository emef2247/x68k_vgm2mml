# PCM target projectionと直接MDX生成

ユーザーが合意したstrict／best-effort方針の最初の実装。独立したMXDRV＋ROM IOCS基準R、
C0/C1直接解析、A/B/B_ref/C比較は未実装。PCM再生器の問題を解消したという記録ではない。

## 実装した境界

- `py/okim6258.py`のimmutable PCM IRは変更していない。
- `py/pcm_mdx.py`でMDX profile、bank/slot、共有clock、型付きtarget命令列を決める。
  同じ命令列から可読MMLと`<stem>.pcm/target.tsv`を出力する。
- helperの`--compile-pcm FM_ONLY.mml PLAN.tsv OUTPUT.mdx`はFMだけをmmlxでコンパイルし、
  FM track／tone／titleを保ってtyped PCMをsoundlogの既存MdxBuilderで追加する。
  PCM MMLの再解析、生バイトの継ぎ足し、新しいコンパイラは使わない。
- FMの有限repeat／escapeを含む共通tempo／終了tick、標準9track、PDX参照、
  serialize後のtyped command一致を検査する。PDXはOUTPUTの隣から解決する。
- `vgm2mml.py`はPCMを含む対応入力からMML＋MDX＋PDXを一度で生成する。
  batchは生成済みMDXを`--from-mdx`へ渡し、可読PCM MMLで上書きしない。

## policyと診断

既定`--pcm-policy strict`は、既知lossを伴う投影をhelper実行前に止める。
`best-effort`は確認済みのfallbackに限り生成する。今回は発音開始時のpanを保持し、
途中pan／mute変更の損失をsource event、元時刻の影響区間、元値／投影値付きで記録する。
次のsource発音にはその時点のpanを明示し、人工的なretriggerを追加しない。

native PCM1のsample length低16bit使用に合わせ、65535 bytes超は既知target制約とする。
切り捨てfallbackは定義していないので両policyで生成を止める。
12-bit出力、非対応rate、source scheduling未解釈も、近似未定義のままbest-effortで通さない。
不正sourceと未確認sourceをfail／unverifiedで区別し、既知lossとunknownを同時に残す。

`*.pcm.assessment.json`／CSVはtarget_projection、runtime_validation、artifactのscopeを保存する。
投影assessmentと総合validation、generated／blocked／error、成果物ごとの状態を分離する。
総合判定はfail優先、次にunverified、lossy、pass。artifact生成エラーも総合failになり得るが、
`validation_run=not_run`はruntime比較を実行していないことを示す。
IOCS reset／実消費nibble数はunverifiedのまま。strictの既知loss停止はunexpected mismatchではない。
失敗時は前回のtargetファイルを無効化し、sourceと診断を残す。部分生成もレポートに明記する。

## 検証と観察

WSLでhelperをrelease buildし、public fixtureのCLI変換を実行した。

```bash
python vgm2mml.py tests/fixtures/public/pcm/reset_pan_hold.vgm \
  --outdir outputs/pcm_target_2026-10-09/strict --dump-passes
python vgm2mml.py tests/fixtures/public/pcm/reset_pan_hold.vgm \
  --outdir outputs/pcm_target_2026-10-09/best-effort \
  --pcm-policy best-effort --dump-passes
python scripts/export_mdx.py tests/fixtures/public/pcm \
  --outdir outputs/pcm_target_2026-10-09/batch --pcm-policy best-effort
```

- strict reset_pan_holdは終了2、blocked／lossy、runtime未実行／総合unverified。
  best-effortは終了0、MML＋MDX＋PDX、同じ3区間のpan lossを保存する。
  影響区間はsource samples [722,1445)、[1445,2167)、[2167,2890)。
- source IR／CSVの途中panは保持され、target panは開始時1と次の発音時2。
  各playbackは256 ticksで一音符に収まり、以前のpan分割に由来する不要なF7／tieは消えた。
- 新規public `long_hold_stop`は1024 bytesの算術pattern。512 ticksを256＋256に分け、
  先行chunkの直前にF7を出力する。その後は通常の終端と休符。
- public3件のtarget最大境界誤差は0／0／1 VGM sample。PDX全slot／payload一致、
  raw MDX header／P命令列、target CSV／manifest／可読MMLを点検した。
- batch3件はpairを保持し、全てpcm_replay_unavailable、VGM欄空、終了1。
  これは予期したガード結果であり、往復成功ではない。
- native OPM public9曲の既存semantic roundtripは9/9成功。
- PCM26、export13、OPM95のfocused Python tests、Rust12 testsが成功。
- 追加の全体suite走行は大型private MGSDRV互換fixture処理中に打ち切った。
  全体suite成功とは扱わず、今回の変更範囲に対するfocused結果を採用する。

生成物と点検結果はignored `outputs/pcm_target_2026-10-09/`。
private歌唱／ROM／sampleは追加していない。これらの検査は構造・投影・静的参照の検査である。

## 次の作業

RのMXDRV版・machine／ROM IOCS・patch有無と、chip/PPI／DMA観測手段を固定する。
自作短いMDX＋PDXからC0意図と、根拠付きC1実効挙動を分けて記録し、
original→R→Aとgenerated→R→B_refを最初のfixtureから確保する。
soundlogを循環oracleにせず、確認済みの規則に限って再生器Pを修正する。
source stream展開とFIFO／decoder消費modelは別の未実装段階である。
