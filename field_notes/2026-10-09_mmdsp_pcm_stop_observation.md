# MMDSPでPCMテスト音が停止しないという観察

ユーザーが生成済みMDX＋PDXをMMDSPで再生したところ、`long_hold_stop`と
`reset_pan_hold`が停止せずノイズが続くと報告した。生成したsampleは算術patternなので
ノイズ状の音自体は想定内だが、継続再生の報告は停止検査の問題として調べる。
既知の途中pan lossを理由に停止不良を許容しない。

ユーザーはこの深掘りを一旦保留し、あるべきデータの生成を最優先とした。
以下は保留中の調査記録であり、追加の環境確認・probe再生依頼や停止処理の変更は
再開の指示があるまで進めない。停止問題を解決済み／再生検証済みとは扱わない。

ユーザーの追加観察：XM6 TypeG Ver3.32、`MXDRV30.x`を使用、PCM8常駐あり。
MMDSPの使用driver表示もMXDRVと確認された。
「演奏終了・停止の表示でも音が残る」と確認された。シーケンサ終了と実音声停止の
違いを調べる必要がある。AUTO／REPEATの設定そのものは引き続き確認中。
現時点の未確認項目：実際のresident driverの版、PCM8版／mode、IOCS patch、
MMDSP AUTO／REPEAT状態。
`opm_pcm_rates`が同環境で正常停止することも未確認である。
ユーザー観察と、generatorの静的検査や独立Rによる検証結果を区別する。

## 点検結果

- latest batch3件とも標準9track、全track終端はF1 00、PDX名／参照sample長は正常。
  tone offsetは全件0で、PCM FDはbank保存だけなので、それだけでは2件の差を説明できない。
- 失敗報告2件はtimer operand255、logical end521 ticks。公称時間は約0.133376秒。
  `opm_pcm_rates`はtimer224、10 ticks。3件とも非常に短い自作テスト音である。
- Native MXDRV2.06+17 Rel.X5-S逆アセンブルでは、note operandFFは256 tickとして
  byte counter0→255→…→0で扱われる。q8のgate counterも同様である。
  FFを不正opcodeと断定してはならない。F7は保持flag、F100は全track終端判定へ進む。
- header／PCM bytes点検はignored
  `outputs/pcm_target_2026-10-09/native_format_review/metadata.json`。
- 既存Leonardo mdx2vgmの未改変binaryは最新3件すべてで終了する。
  これはnative由来の移植シーケンサが終了することだけを確認する。
  既知のPCM STOP stub／rate／pan問題があるため、VGM／IOCS／実機oracleにはしない。
  記録は`outputs/research/mdx2vgm_stop_probe/`。

同portの診断用copyに2000 tick上限と呼出し／counterログを追加した結果：

| case | ADPCMOUT tick | ADPCMMOD_END tick | 全track終了tick |
|---|---|---|---|
| long_hold_stop | 0 | 0, 512 | 522 |
| reset_pan_hold | 0, 265 | 0, 256, 265, 521 | 522 |
| opm_pcm_rates | 0, 8 | 0, 8, 8, 10 | 11 |

全件の終了時maskは0、fatal errorは0だった。256 tick音符のcounterも正常に
wrapした。これらの経路はparameter0のENDを呼び、parameter1のSTOPは呼ばない。
ENDはportでは空実装のため、これは停止要求のintentとシーケンサ終端の確認に限る。
実IOCS／DMA／音声の停止を証明しない。full tick CSVとsource provenanceは同folderの
`README.md`に記録した。

## 再現環境の候補ファイル

指定されたXM6 folderの`xm6g.ini`は共有folderとして`H:\_env\D`を設定している。
その`BACKUP2/usr/local/music/mmsdp`に以下の候補を発見した。embedded bannerだけを
点検し、実行・設定変更はしていない。backupの存在は実際の常駐状態を証明しない。

| filename | embedded banner | SHA256 |
|---|---|---|
| mxdrv30.x | MXDRV 2.06+16 Rel.3 | 3459f9a598481ae8ed82b471851f2ea9ea1b6d5e9347d7e7634c03d67596dac3 |
| PCM8A.X | PCM8A v0.60 | 836194deb1ec872aabf85797c17aa40a954c58f98eb40034d31ed6546f968da1 |
| MMDSP.r | MMDSP v0.30 | 2b0e7b0d1d0dcc76dacbbc45e4b7762417bbb5bebf74301a60c15281dfc8b9e4 |

候補folderの`!Start.bat`はPCM8AとMADRVを起動し、MXDRV30行をcomment outしている。
ユーザーはMMDSP表示がMXDRVであると確認したため、backup scriptを現状とみなさない。
MXDRV30というfilenameをversion3.0と解釈せず、residentの実版を確認する。

今回のMDXは標準9trackでE8 PCM4/8宣言なし。PCM8常駐だけで拡張modeへ移行したと
判断しない。[MXDRVデータ資料](https://w.atwiki.jp/mxdrv/pages/23.html)は+16世代の
標準9trackとEX-PCM宣言を記述するが、該当binaryのruntime保証ではない。
[PCM8A v1.02 manual](https://github.com/kg68k/pcm8a/blob/main/docs/pcm8a.txt)は
IOCS/TRAP2経路とmodeの違いを記述し、
[作者のVector配布説明](https://www.vector.co.jp/download/file/x68/art/fh059637.html)には
強制停止処理変更・TRAP2/IOCS出力停止bug修正がある。候補v0.60にその修正内容を
直接当てはめたり、PCM8Aが今回の原因だと断定したりしない。

## MMDSP差分probe

`outputs/pcm_stop_2026-10-09/make_probes.py`で生成した。
両caseに同じPDXと以下のMDXを用意し、MDX8個＋PDX2個を
`outputs/pcm_stop_2026-10-09/mmdsp_stop_probes.zip`にまとめた。
各filenameは短くし、PDX内部参照名は元のまま保つ。

| ファイル | 音符上限 | timer | 公称指示時間 |
|---|---|---|---|
| base.mdx | 256 | 255 | 約0.13秒。元生成物とbyte一致 |
| split255.mdx | 255 | 255 | 約0.13秒。保持を追加してlogical timingを維持 |
| tempo224.mdx | 256 | 224 | 約4.27秒。音符列を維持、指示時刻を32倍に伸ばす |
| both.mdx | 255 | 224 | 約4.27秒。分割とtimer変更 |

timer変更版ではsampleのF4 rate自体を変更していない。
source fidelityを保つ修正版ではなく、停止問題の切り分け用である。
全probeでtyped builder／FM shared tempo/end／PDX静的参照検査は成功し、
base byte一致、全logical duration521、sample byte共通、split版の音符上限を確認した。
MMDSP再生結果は全probe未確認。

まずAUTO／REPEATを無効にしてbaseを単曲再生し、自動再演奏と停止不良を分ける。
継続する場合は差分probeの結果を取る。再生環境と観測結果から原因を絞るまで、
normalizer／gate／EOF／IOCSモデルを推測で変更しない。
canonical source IR、target projectorとhelperのproductionコードは今回変更していない。
