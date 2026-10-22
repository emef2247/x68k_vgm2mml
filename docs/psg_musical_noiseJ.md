# PSG／SSGの発音解釈と限定ノイズ投影

## 共通の発音単位

PSG／OPNA SSGの不変なSegmentから、一時的な44100 Hz source sample単位のビューを
作り、MSX／mucom側でも使う`mml_envelopes.extract_notes`を適用する。
ソフト音量の減衰・同値は1発音内のvolume runにまとめる。音量上昇、pitch書き込み、
設定・shape変更は推定した発音境界となる。これは観測Keyではなく解釈であり、
元のState／Segments・時刻・ゼロ長の制御列を変更しない。

`psg_note_units.py`はMGSDRVの音価グリッド、MML、envelope bank制限を持ち込まない。
抽出したnote IDはsource ch内で識別し、正時間の元rowに対応する。ゼロ長pitch／shape
書き込みは次の正時間区間の境界判断へ引き継ぎ、単独では推定Keyを作らない。
音量run／note所属にないゼロ長の元制御も、投影writeとして順序を保つ。

既存PSG解析が最後の書き込みで区間を終了した場合、最後の既知状態を実際のVGM EOF
まで保持するビューを作る。架空のmute・release tailを追加せず、元Segment終端は保持。
`source_interval_extensions`に元終端・解釈終端・元row・理由を記録する。

OPM側ではこの境界でKey-Off→制御更新→Key-Onを推定する。従来の「可聴状態が
続く限り1発音」というPSG方針からの変更であり、位相・聴感の一致は保証しない。
SCCは従来のaudibility-edge解釈のまま。構造化と音価正規化は既存OPM処理へ接続する。

曲ループは既存の2周解析・保持状態を使う。ループ境界そのものによる再発音や、
EOFでの消音をループ途中へ入れない。元のpitch／volume等が発音境界を示す場合は別。

## 最初のノイズ対応範囲

既定の`--psg-model fm`で、固定音量のnoise-only（mode 2、HW envelopeなし）を
1つのsource partに限り近似する。正時間の該当区間を持つ先頭source chを全曲の所有者
とする。ゼロ長だけの一時状態は予約を取らない。複数パートを合成・動的に使い回さない。

- 単独PSG／SCC: SCCのA..Eは固定。PSGのF..Hを置換し、所有者をOPM7/Hへ配置する。
- OPNA: FM優先と保持tailの予約を維持する。容量内で残すSSGパートを先に選び、
  その中のnoise所有者へ実際のOPM7を予約する。他パートは残ったchを使う。
- AL7/FB0のC2だけを使い、他operatorをTL 127にする。tone復帰時はAL/FB・全MUL/TL・
  NEを元のFM profileへ戻す。共有reg 0x0Fは通常のchアドレス置換をしない。
- 有限曲の終端ではKey-Off・消音とNE解除を行い、ループ再生の末尾では保持する。
- tone＋noise（mode 3）、HW envelope、別source chのnoise、確保できないch7、
  additiveモデルのnoiseは引き続きエラー。`--force`時は理由付きで未対応区間を省略する。

AYの公称noise shift rateを`effective source clock / (16 * max(1, period))`、
OPM側を`4 MHz / (32 * (32-N))`とし、対数比が最も近いNを選ぶ。
Nは今回の保守的な方針として0..30に限定する。N31の除外を確定したHW仕様としない。
範囲の端で大きなレート誤差が生じ得る。LFSR・位相・スペクトル・ゲイン・実機音の
一致を意味せず、エラー値を伴う近似である。SSGは各Segmentのprescaler後の実効クロックを使う。

分周モデルの参照は[MAME AY](https://raw.githubusercontent.com/mamedev/mame/master/src/devices/sound/ay8910.cpp)、
[YMFM OPM](https://raw.githubusercontent.com/mamedev/mame/master/3rdparty/ymfm/src/ymfm_opm.cpp)と
[レジスタ定義](https://raw.githubusercontent.com/mamedev/mame/master/3rdparty/ymfm/src/ymfm_opm.h)。

## 中間結果と使用方法

追加オプションは不要。通常の`vgm2mml.py`／`scripts/export_mdx.py`を使い、詳細保存は
`--dump-passes`を指定する。従来のsource/target CSVは残す。

| 成果物 | 内容 |
|---|---|
| `<stem>.psg.music.csv` | source sample単位の発音・休符・volume runs、元row／event所属 |
| `<stem>.ssg.psg.music.csv` | OPNA SSGの同じ解釈結果 |
| `.opm_target.csv` | 元rowと推定note ID・終端、final/基準track、noise周期・実効clock・N・レート・cent誤差 |
| `.opm_target.json` | PSG基準ch割当、noise所有者、EOFまでの区間補完 |
| `.opm_performance.*` | 推定attack/retrigger/release、元制御・write所属 |
| `.opna_channel_allocation.*` | OPNA混在入力の最終ch割当（SSG基準trackからの置換先） |

noise区間のtone周波数・pitch誤差欄は空欄とし、専用noise rate欄を読む。内部のKC/KFは
carrier初期化用の値で、観測した音程ではない。未対応省略は既存force一覧にも残る。

確認範囲は小さな自作データのsource不変、volume run、zero-time、割当競合、mode復元、
保持ループ、MML生成と中間結果。実曲リグレッション・実機視聴は別途行う。
