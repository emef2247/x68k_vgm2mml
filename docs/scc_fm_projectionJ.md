# SCCからOPMへの音色投影

現在の対象はx68kのMDX経路です。既定のFM＋加算合成（`fm-additive`）を含め、SCCの1chへ
最大2つのOPM chを割り当てる任意指定のモデルを用意しています。
音源として観測されたSCCのState／Segment／32-byte波形は変更しません。

## すぐに使える2ch加算合成

```sh
python vgm2mml.py input.vgm --outdir outputs/scc_additive8 \
  --scc-model additive8 --dump-passes

python scripts/export_mdx.py input.vgm --outdir outputs/listen/scc_additive8 \
  --scc-model additive8 --compiler mmlx --no-vgm
```

`additive`はDFTの第1〜15高調波から振幅の大きい4成分を選びます。
`additive8`は、残る成分から次の4成分を補助chへ割り当てます。どちらもAL7です。
波形ごとの音量正規化は行わず、共通の`--scc-gain`（既定0.125）とSCC音量を
掛けます。DC、第16高調波、任意の位相は再現しません。DFTの保持エネルギーは
聴感上の改善率や実機波形一致を意味しません。

## 発音、SWエンベロープ、構造化

`py/scc_note_units.py`は、MSX側と共通の`mml_envelopes.extract_notes(...,'scc')`
を元のサンプル時刻で利用します。同一設定・連続区間の一定／下降音量は一つの
発音内のrunとなり、音量上昇、音程書き込み、波形ID・enable等の設定変更は
新たな発音単位になります。長さ0の音程書き込みも、次の正時間区間の境界に
反映します。SCCにネイティブなOPM Key-Onがあるという解釈ではありません。

最終観測状態は、後続状態がない場合だけ、明示されたVGM終端まで持ち越します。
延長前後の時刻は`opm_target.json`の`scc_source_interval_extensions`へ記録します。
元のSegmentの長さ・音量・波形は書き換えません。

両方のOPM chは同じ発音単位と音量runを参照します。FM音色のSW音量変化は
**キャリアTLのみ**に反映し、変調器のTL／変調指数を維持します。Key境界や
波形変更時の位相はSCCと一致しません。MGSDRV固有の`@e`表記やエンベロープ
バンク制限はMDXへ持ち込みません。TLの0..127という範囲や全chのミックスに
よる飽和まで解消するものではありません。

発音単位の反復構造は共有の`source_plan`／`SourceLoopPlan`で監査用CSVへ保存します。
最終MMLは、明示的なOPM演奏計画→生成OPM VGM→通常のOPM musical／structure
経路で、制御runや有限反復を構造化します。この経路もMSX由来の共有ループ解析を
利用します。MSXのMML文字列を流用したり、Segmentごとに音符とtieを作ったりは
しません。発音単位の監査用構造と、最終ターゲットの構造は区別してください。

既存の`--normalization-ms`とVGM曲ループの処理は、この投影にも適用されます。
音価の省略・時刻補正はターゲット側で行い、元の発音単位・Segmentは保持します。

## チャンネル予算

OPMは8chです。SCCの主ch（A..E）、PSGの固定割当（通常F..H、ノイズ使用時は
その範囲内で並べ替え）を先に予約します。予約はループ再解析分を含む全入力範囲で
行い、途中の休符だけを利用したchの貸し借りはしません。初期化命令を出す
非発振のSCC chも予約対象です。

補助chの優先度は、改善量×元区間長×(元音量/15)^2の合計です。`additive8`では
追加DFT成分のエネルギー、FMモデルでは基準音程の測定誤差の減少量を使います。
SCC全5chを一律2chへ拡張することはできません。空きがなければ、そのSCC chは
従来の1ch加算合成を使います。主chやPSGを品質向上のために省略しません。

## FM音色バンクを使う

FMモデルで`--scc-voice-bank`を省略すると、解析した発音波形を自動探索します。
`<stem>.scc.waveforms.csv`と`<stem>.scc.voice_bank.json`はMMLと同じ出力先に残ります。
探索結果のキャッシュは`.tools/scc-fm-fit/cache/`です。波形・clock・gain・core・
探索版が同じ場合は探索を再利用し、音程転用の測定値も記録します。初回探索には
GCC・NumPy・外部YM2151 coreが必要で、不足時は準備方法を示して停止します。

既存バンクを明示する従来の手順も使用できます。

```sh
python vgm2mml.py input.vgm --outdir outputs/scc_source --dump-passes

python scripts/fit_scc_fm.py outputs/scc_source/input.scc.waveforms.csv \
  --outdir outputs/scc_fit --audio

python vgm2mml.py input.vgm --outdir outputs/scc_fm \
  --scc-model fm-additive --scc-voice-bank outputs/scc_fit/voices.json --dump-passes

python scripts/export_mdx.py input.vgm --outdir outputs/listen/scc_fm \
  --scc-model fm-additive --scc-voice-bank outputs/scc_fit/voices.json \
  --compiler mmlx --no-vgm
```

`fm-additive`はFM＋加算、`fm-fm`はFM＋FMの候補を選びます。
同じ探索コマンドへ複数の波形CSVを渡せば、内容の重複を除いて一つのバンクへ
まとめられます。入力曲に必要な波形・モデルがバンクにない場合は停止します。
探索ツールの外部YM2151 core、GCC、NumPy、探索範囲と測定方法は
[音色探索の仕様](scc_fm_fit.md)を参照してください。通常の`additive8`には不要です。

採用条件は基準音程での加算合成より測定誤差が小さいことです。改善しなければ
1ch加算合成へ戻します。補助パートが無音の候補はchを消費せず、主chだけを使います。
2つの有音パートが必要な候補で補助chを確保できない場合は、片方だけを使わず、
元の1ch加算合成へ戻します。

バンクは波形32-byte全体のSHA-256で照合します。YM2151／4MHz、基準gain・音程、
探索版、core／wrapperのハッシュ、測定レート・フレーム数、キャリア校正値と
音色パラメータの形式を検証します。ローカルに同じcoreを要求しないため、別環境で
生成したバンクも利用できます。来歴の記録は音色の正しさや外部ファイルの真正性の
証明ではありません。

採用判断は基準音程の測定です。バンクの`pitch_checks`は記載音程での限定した
転用評価で、全音域・SW音量変化中・波形切替中の音質を保証しません。
FMが加算合成より良いという一般則は置きません。実機の聴講は別途必要です。

## 中間結果と選択理由

FMまたは補助chモデルでは`<stem>.scc.voice_projection.json`を通常出力にも保存します。
主ch／予約ch、補助chの割当、波形ごとの採用理由・基準誤差・バンクのハッシュを
確認できます。`quality_fallback_one_lane`はch不足による1chへの後退です。

`--dump-passes`では、以下も保存します。

- `.scc.music.csv`: 元時刻の発音単位、波形、元Segment行、SW音量runと推定の由来。
- `.scc.music.chN.structure.csv`等: 発音単位に対する共有構造解析と元行の対応。
- `.opm_target.csv`／`.opm_writes.csv`: 物理target track、`target_lane`、音色、TL、元行。
- `.opm_voices.csv`: 加算音色またはFMのalgorithm／feedback／MUL／TL／carrier。
- `.opm_performance.*`: 各物理chの推定Key、制御書き込みと元発音単位の対応。
- `projected_opm/`: 通常OPM経路が消費した生成VGM、発音・制御・構造化・正規化の中間結果。

試聴エクスポートではJSON・CSV等の詳細は出力先の`_diagnostics/`に保存されます。
明示的な1ch加算モデルおよび旧`opm-additive`互換別名の最小出力ファイル構成は維持します。詳細設定は`--dump-passes`時の
`.opm_target.json`にも含まれます。

## MUCOM側への適用

今回の実装・確認はx68k側です。SCCの元発音／SW音量run解釈と音色探索基盤は
再利用できますが、MUCOM側はOPNAのFM6chの予算と、YM2608による音色測定が
必要です。YM2151用のバンクをYM2608の確認済み音色として扱いません。

## 音源別の比較出力

`--psg-only`（`--psg_only`）と`--scc-only`（`--scc_only`）は排他指定です。
Raw VGM、両音源のState／Segment、元時刻の発音・SW音量runは解析したまま、
ターゲットへ渡す音源だけを選びます。選択と除外元音源はconversion JSONへ記録します。
除外したPSGのノイズ／HWエンベロープでSCC-only出力を停止させません。
SCC-onlyではPSG用chを予約しないので、既存の割当規則内で補助chが増える場合があります。
これらはMDXのPSG/SCC入力経路用で、MGSDRV互換出力・ネイティブOPM入力用ではありません。
