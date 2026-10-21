# PSGからMDX用PCMへの投影

`--psg-output pcm`は、PSGをOPM chへ割り当てる代わりに、連続するPSG3chの
音声を一つのモノラルPCMへまとめます。SCCは通常どおりOPMへ投影します。
PSGの大量の制御命令をMDXのFMトラックから除き、PSGノイズとHWエンベロープも
音声へ焼き込みます。元のState／Segment／発音単位は保持します。

## 準備と使い方

WSLのPython3、GCC、NumPyおよび通常のPCM用Rust helperを用意してください。
外部PSGコアを固定リビジョンで取得するセットアップは以下です。

```sh
bash scripts/setup_psg_pcm.sh

python scripts/export_mdx.py INPUT_DIRECTORY --outdir outputs/listen/psg_pcm \
  --psg-output pcm --pcm-policy best-effort --compiler mmlx --no-vgm
```

通常の全ツール準備にも`bash scripts/setup_tools.sh --with-psg-pcm`を指定できます。
`--psg-output`の既定は`opm`です。再圧縮を伴うため、PCM出力は
`--pcm-policy best-effort`を明示します。`strict`は診断を残して停止します。

PSG単独を聴く場合は`--psg_only`を追加します。`--scc_only`と`--psg-output pcm`
は併用できません。`--pcm-profile low`／`ultra_low`、`--force`の容量超過省略も
共通PCM投影の規則を使用します。GUI・実機での再生確認は別途必要です。

このモードはMDXのPSG/SCC入力向けです。OPNA内蔵SSGやYM2149／AYの別variantを
暗黙にこの経路へ移しません。現行対応はVGMのAY type0、単一instance、flags0..3。
同フラグは出力配線等のヒントとして記録し、3chのセンターモノラルミックスにします。

## ソース解釈とターゲット変換

ソース再生は、外部の[emu2149](https://github.com/digital-sound-antiques/emu2149)
を固定commit `441f3dc295a9b82db16921461f0678b483db8304`で利用します。
コアのソースは`.tools/emu2149/`、作成したラッパーと共有ライブラリのハッシュは
再生JSONに記録します。外部コードをこのリポジトリへコピーしません。

Raw VGMの0xA0を元の順序で一度ずつ処理し、44100Hzの元サンプル時刻に合わせて
適用します。3chが一つのノイズLFSRとHWエンベロープを共有し、同値のreg13書き込みも
一度の再開始として扱います。Trace CSVの3chへのbroadcastを再生命令として
流用しません。推定した音符／SW音量runの境界で音源をresetしません。

初期化はAY音量モード2、quality1、先頭で一度resetという明示したコアのモデルです。
quality1のrate converter／高周波抑制は実機回路の検証ではありません。特に音程period0の
DAC状態等はコアの高周波抑制の影響を受ける場合があり、全AY動作の完全再現は主張しません。
I/Oレジスタ14/15の値は保持しますが外部周辺機器はエミュレーションしません。

元の正電圧DACミックスはsource WAVへ保持し、ターゲット側で別の音声viewを作ります。
20Hz一次high-passと63tapの中心対称Hamming-windowed-sinc low-passをかけてから、
共通PCM packagerでMSM6258 ADPCMへ再圧縮します。cutoffは選択した出力レートの0.45倍。
`--psg-gain`（PCMモードの既定1、範囲0より大きく1以下）を適用します。
波形・区間ごとのピーク正規化は行いません。原音声はフィルタ結果で上書きしません。

これは帯域・位相・量子化の近似です。有限長FIRのpre-ringing、端のzero padding、
元のactive span外のfilter tail省略があり、アナログ出力回路の再現ではありません。
その後の共通packagerは線形補間を使うため、完全なalias除去も保証しません。

## 時刻と曲ループ

初回と既存readerの再解析分を、PSG runtimeをresetせず連続して再生します。
SCCの生成OPM VGMも、このモードに限り元サンプル時刻で出力します。
同一MDX tick内に複数chの書き込みがあっても、元時刻が逆転しないよう再整列します。
EOF／選択した曲ループ境界はPCMと同じ元時刻を持ち、OPM側で再度ループ展開しません。

最後にFMとPCMを共通MDXクロックへ投影します。PCM chunk境界も元→最終時刻の
許容誤差確認へ含め、正時間のPCM区間は潰しません。共通packagerの最寄り偶数サンプル
への丸めは、選択したPCMレートで最大1サンプルの長さ誤差です。

PCMは記録した一回分をPDXへ固定するため、`L`以降を繰り返す際の波形は固定されます。
無限に動くPSGの後続LFSR／発振位相そのものを毎周再計算するわけではありません。
chunkごとの独立ADPCM predictor resetの仮定も診断へ記録します。

## データ量と再利用

これは音符ごとのドラムサンプル化ではなく、連続ミックスの区間音声です。
音程・音量が同じでもノイズ／発振／エンベロープの開始状態が違えば別音声になります。
初版は**実際のADPCMバイトが一致するchunkだけ**を再利用します。
音符単位の強制phase resetによる再利用は、別の近似として今後検討します。

MMLの命令量は減らせても、PDXは発音している時間に応じて増える場合があります。
既存の96slots／1sample65535bytesの検証範囲、共通PCMプロファイル・容量診断を使用します。
MMDSPのADPCMバッファやSCC側のトラック容量に収まる保証はありません。

## 中間結果

- `.psg.ordered_writes.csv`: 元address／event ID／反復番号／時刻を持つ一回ずつの書き込み。
- `.psg.playback_gates.csv`: 音量またはEG選択が非ゼロの保守的なactive spanの和集合。
  すべてのmixer入力を無効にしたDAC状態も含み、聴覚上の無音判定とは区別します。
- `.psg.native.wav`／`.psg.playback.json`: フィルタ前のコア出力とcore・初期化・設定の来歴。
- `.psg_pcm_mapping.csv`／`.psg_pcm_bridge.json`: 元span、出力chunk、sample ID、profile、
  フィルタ・mono・ADPCM・共有clockの損失と誤差。
- `.pcm_*`と`.pcm/`: 通常と共通のPCM IR・binding・型付きMDX命令・容量診断。
- `projected_opm/*.source_map.csv`と`provenance.json`: 元サンプル単位でserializeしたOPMと
  最終MDX時刻の対応。既存`.opm_performance.*`の丸めtick診断とは分けて示します。

解析・中間結果はこのモードで保存し、試聴exportでは`_diagnostics/`以下へ残します。
音声出力・生成成功は実機再生や原音との一致の証明ではありません。
