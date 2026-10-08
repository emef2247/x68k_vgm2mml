# 2026-10-08: PCM/PDX初期実装と検証

設計検討後、ユーザーの「提案の内容で実装を進めてください」を受けて実装した。
前提は `2026-10-08_pcm_pdx_design_review.md`。通常入口は引き続き `vgm2mml.py`。
これは初期対応の完了と残件の記録であり、X68000 VGM全形式への対応完了ではない。

2026-10-09追記: [再生意味論の追加調査](2026-10-09_pcm_mxdrv_roundtrip_review.md) と
[独立往復検証の設計](../docs/pcm_roundtrip_validation.md) を優先する。
以下の123/8件は当時の構造・byte保存等の検査であり、標準MXDRVの実効pan/resetの認証ではない。
調査したnative版ではFC/EDは次の新規PCM開始へlatchされる。保持中panのタイ出力は忠実性未認証。

## 実装

- OKIM6258 clock=0x90、options=0x94をversion/data_start境界付きで読む。
  往復監査がOKIM6295の0x98を誤読していた点も修正した。
- `py/okim6258.py`にimmutableな生転送／制御状態／再生span／符号化sample tableを追加。
  数百万件のbyte書き込みはpacked列で保持する。source event ID/address/timeを追える。
- データ供給とdecoder消費を区別する。`consumed_nibbles=None`、`nominal_nibbles`は計算値。
  `reset_observed`とfresh-VGM初期resetの仮定を分け、PLAYの連発を再発音扱いしない。
- codec＋符号化bytesの完全一致でsample_idを共有する。hash衝突も実bytesで確認する。
  sampleの速度・pan・resetは再生spanに属する。
- `py/pcm_mdx.py`にMDX専用bindingを一度だけ構成し、MMLとPDX manifestで共有する。
  `P @0 F4 p3 q8 @v127 n0,16`のような通常sample音符を使用する。
  長い保持と保持中pan変更はタイ、有限反復は既存planner/compactionを使用する。
- PCM/OPMのsource境界とcontrol時刻を一つのscore clockで検査する。6 VGM samples以内。
  boundaryごとのtarget時刻・誤差はPCM projection/clock CSVにも残す。
- 既存Rust helperのsoundlog `PdxBuilder`を使用する。Python側でも96件のBE offset/lengthと
  canonical bytesを独立照合する。WAV decode/re-encodeや独自PDX encoderは追加していない。
- `--pcm-generator PATH`を追加。OPMのみのMML変換はPythonだけで実行できる。
  sampleがないSTOP/pan設定だけの入力は空PDXを要求しない。
- PCM-onlyとOPM+PCMを通常native pipelineへ接続した。付随して全無音OPMおよびPSG投影の
  共通終端までの休符出力を確認した。架空のOPM key-onや音色は作らない。

初期対応は直接B7、単一OKIM6258、4-bit low-first、10-bit出力、標準F0..F4、bank 0／96 slots。
source IRにはPDXのslot上限を入れていない。12-bit sourceは設定とbytesを保持してMDX側で拒否する。
MAME X68000構成は10-bit、decoder clampは出力精度で異なり、PDXにはそのモード指定がない。

## 外部ツールの制約と対処

mmlx 0.2.0はPだけでも16 track＋PCM8 markerを作る。helperに
`--compile-only INPUT.mml OUTPUT.mdx --pcm-mode standard`を追加した。
inactive Q..Wを検査し、typed documentを9 trackへ選択、markerを除き、serialize/reparseして
header/bodyを一致させる。外部コンパイラの置換ではない。
PDXの名前解決・存在・全static referenceの非空slotを検査してからMDXを保存する。

soundlog 0.15.0には標準PCMのraw継続／停止／resetの問題がある。
triple tieのinterior KeyOffDisableやpan/F命令でraw cursorがクリアされる。
短い二つの発音でもB7 PLAY/STOPは曲全体の一対だけで、元VGMのreset関係を保持できない。
標準MXDRVが音符ごとに物理resetするかはIOCSまで確認が必要であり、この実験だけで断定しない。
cursorクリアだけを消すとkey-off後にもcursorが進むため、単純patchはしなかった。

PCM→VGMを検証成功とは扱わず、helperはvalidated MDXを保存後に明示エラーを返し、
古い指定VGMを削除する。バッチはMML/MDX/PDXを保持して `pcm_replay_unavailable`、終了コード1。
FMのみの再生は維持した。原bytes保存と再生波形同等は別の主張である。

## 実施した検証

- WSLの関連Pythonテスト **123件成功**。source 14件、target 15件のほか、reader、native
  projection/music/structure/tracks/fixtures/batch、compaction、exporter、PSG/SCC projectionを含む。
  inherited compatibility全suiteの成功を主張しているわけではない。
- Rust helper **8件成功**、locked/offline release build成功。slot 95、odd byte length、空slot、
  manifest/path検査、欠損PDX、標準9 track選択、stale VGM削除、外部replay不具合を検査。
- architect完了前レビューP1（12-bit無条件受理）はtarget reject＋対照テストで修正。
  P2（PCM finite loop/tie証拠不足）は通常版・compact版をmmlxでコンパイルし、typed有限反復を
  テスト内で展開してNote/length/KeyOffDisable/Pan/F/volume等のordered command一致で補った。
- `tests/fixtures/public/pcm`の2ケースは完全自作byte patternで、ゲーム／ROM音声なし。
  reset/retrigger、pan left/right/mute/center、asset共有、OPM同時再生とF0/F4切替を含む。
  independent schedule/hashをJSONに保持し、PDX payloadとcompiled MDX header/holdを検査。
- 既存native公開9ケースの往復 **9/9成功**。
  `outputs/pcm_pdx_2026-10-08/native_regression/`に結果を保存した。
- PCM公開2ケースのCLI/pass生成・バッチを確認。2件とも意図した
  `pcm_replay_unavailable`、MML/MDX/PDXあり、VGMなし。
  `outputs/pcm_pdx_2026-10-08/public/`、`public_batch/`、`external_acceptance/`を確認。
  state/segments/binding/projection/MML/PDX tableを検査した。private bytesの公開物への移動なし。

基本コマンドはREADMEと `docs/pcm_pdx.md`。fixture再生成は
`python tests/scripts/generate_pcm_fixtures.py`。単体検証は例えば
`python -m unittest discover -s tests/scripts -p test_pcm_mdx.py -v`。

## 次の作業

1. 不規則なdirect supply／stream schedulerに対する独立した時刻・FIFO・decoderの検証を用意する。
   0x04/0x44と0x90〜0x95は現在raw保存のみで、未対応を明示する。
2. KMSM009はbytesを抽出できるが12番目の供給でstrict lattice検査から外れる。
   expected=約62.0928、actual=61 VGM samples。許容誤差を広げて成功にしない。
   この例は一曲連続のsoftware生成波形で、元の個別PDX voiceを復元したわけではない。
3. trusted PCM player／修正済み外部再生と独立基準を用意してから音声比較を進める。
   MMDSP／実機／エミュレータの再生・GUI確認は未実施。
4. 複数bank、曲loopのdecoder continuation、その他codec/rateを必要に応じて拡張する。
   先にsource evidenceで表現できることを確認し、target都合をsourceへ戻さない。
5. 将来Z_MUSICのversion/compiler/ZPD writerを選ぶ。現source IRと別binding/backendを使う。

workspaceはWSLと同じI:共有ファイルで、コピー反映は不要。コミットはユーザーが行う。
英語commit案: `Add inspectable OKIM6258 PCM conversion and standard PDX output`
