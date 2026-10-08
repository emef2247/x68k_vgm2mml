# PSG/SCCの音楽的投影を通常OPM→MDX経路へ接続

## 要求と採用方針

ユーザーは、Segmentの写像をyコマンドとタイで連結する方式ではなく、
整備済みの通常OPM→MDX MML生成パスを使うことを再確認した。
MMDSPのレベル／鍵盤表示と大きい出力サイズはMSX側にも記録済みであり、
旧加算モデルのタイ保持を再実装することは目的ではない。

PSG/SCCにはOPMのKey-On信号がないため、発音区切りに推定が必要になる。
ユーザーは「音楽的な発音区切りを優先し、位相変化を明記して検証する」を選択した。
可聴状態の立ち上がりを発音開始、立ち下がりを終了として投影する。
音程・音量の変化だけでは再発音しない。GUI用の周期的Key-Onも入れない。
これはターゲット投影の判断であり、ソースSegmentや観測値を変更しない。

## 確認した既存実装・資料

- `msx_vgm2mml/field_notes/2026-10-06_mdx_display_regression.md`:
  68件中57件の旧加算MML検証と、MMDSPの表示／バッファ問題のユーザー報告。
  全曲保持・繰返しsetter・無音を含むタイが旧方式の問題として記録されている。
- MSX側の`py/additive_mdx_notes.py`とテスト: AL7/FB0の保持音符とタイ。
  旧比較は可聴・正時間区間とKey edgeを中心とし、無音のpitchや同時刻の全順序は対象外。
- MSX側の`py/segment_utils.py`: 継続、portamento、vibrato、envelopeの判定契約。
  `kl`はpitch/voice/volume変更でリセットされるため、単独で変化中の保持の証拠にしない。
- assetsの`psg_scc_voice_by_fmchip/MS.X開発秘話-電子版-v1.0.pdf`、印刷pp.52–53:
  保持KeyとL/R muteを分けるPSG→OPM実装の記述。
- assetsの`docs_yamaha/yamaha_ym2151_synthesis.pdf`、PDF pp.6/10/15:
  operator別Key、EG release/TL、独立L/R出力。ハードウェア資料でありMDXのタイ仕様ではない。
- `WING01.png`～`WING03.png`: FM音色例として確認。今回、音色マッピングは変更しない。
- 使用中のmmlx 0.2.0／soundlog 0.15.0のローカルソース:
  raw Key-OnはMDXのnote状態を設定しないため、その後に最初の通常音符を置くと
  追加Key-Onになり得る。初期保持Keyを残したまま音符を差し込む方式は採用しなかった。

## 実装

`PSG/SCC source → 既存Segment → 保持投影baseline → 推定した音楽的投影 →
生成OPM VGM → opm_conversion.convert → 通常の構造化MDX MML`

- `py/opm_performance.py`: baselineを変更せず、元write ID・source row/sampleに
  対応する推定gate計画を作る。初期保持Key-Onを除き、発音設定の後にKey-On、
  mute制御の前にKey-Offを置く。zero-timeの推定変化も保持する。
- `py/opm_target_vgm.py`: 実在するOPM中間VGMを生成する。対応CSVにcommand address、
  waitを含む全コマンドのevent ID、元write ID、source sampleを記録する。
- `py/psg_scc_conversion.py`: 生成OPM VGMを既存のOPM変換器へ渡す。
  投影OPMのCSVには`state_origin=projected_opm`を付け、元PSG/SCCにOPMがあったとは扱わない。
  `provenance.json`にsource/target hash・設定・3段階の時刻を残す。
- 最終時刻と元source sampleの差を全write・終端で直接計算し、最大12 samplesを検査する。
  既存の各段6 samplesの境界を合成した値で、音価正規化は追加していない。
- `--target opm`／`opm-additive`の既定は構造化経路。
  `--notation registers`は従来の保持投影、`--no-loops`は有限反復を無効化する。
  dumpなしでは従来どおりMMLだけを残し、一括出力スクリプトも新しい既定経路を使う。
- 通常OPM生成器の最終整形を`render_music_tracks`へ抽出。初回抽出では公開9件の
  3種類のMML（27比較）がバイト一致した。
- 通常OPMの共通音量判定を飽和TLに対応させた。飽和したcarrierを含む場合も、
  全operatorとraw TLが厳密に再現できる場合だけ`@v`にする。
  これによりAL4の固定TL127 carrierと可変carrierを、正しい共通音量として表せる。

## 最低限の検証と中断

- 関連115テストが成功。OPM reader/Segment/MDX/構造/音価補正、PSG/SCC投影、
  新しい推定Key・中間VGM・来歴・比較、一括出力を含む限定集合。
  全リポジトリの既存失敗を含むsuiteは再実行していない。
- 公開ネイティブOPM `tests/fixtures/public/opm/from_mdx` の9件すべてが
  既存の外部MML→MDX→VGM検証で成功。
- 公開トーンの下表3件は新経路の外部検証に成功。
  全既知状態（無音を含む）、Key命令の時刻・値、Key直前／直後の状態、終端を確認。
  3件ともfallback理由なし。初期化等の必要なraw制御は残るが、Segmentごとのraw連結ではない。
- 各公開トーンで既存source/pass/baselineの27ファイルが作業前とバイト一致。
  新しい音楽的Keyの起源・元write対応・投影CSVと中間MMLも確認した。

| 公開入力 | 発音単位 | MML bytes | MDX bytes | Key前後状態不一致 |
|---|---:|---:|---:|---:|
| volume_sweep | 16 | 3693 | 1533 | 0 |
| scale_chromatic | 13 | 3339 | 1329 | 0 |
| short_pulses | 4 | 1434 | 546 | 0 |

生成物・結果は`outputs/opm/structured_psg_2026-10-08/final_public/`と
`final_native/`に保存。全制御の文字列／順序一致やPSGとの音響同一性を主張しない。
推定Keyによる位相変化は選択した近似。MMDSP GUI、試聴、ローカル曲の容量は未検証。
vgm-convとの新しいサイズ比較も実施していない。

ユーザー指定により、この最小公開検証が通ったところで中断した。
最終レビューで**全無音入力が新しい構造化経路では失敗する回帰**を確認した。
OPM writeがなく後段のSegmentからchip情報を得られないためで、発音を捏造せず
無音終端を表す処理と変換全体の限定テストが再開時の最優先事項。
次にローカルトーンで音・サイズ・GUIを確認し、その後でノイズ／EGへ進む。
新しいノイズ用資源配分、音色、gain、範囲、音価補正は今回変更しない。
