# 2026-10-08: ネイティブX68000 PCM / PDX対応案の検討

実装後の状態・検証・残件は [PCM/PDX初期実装](2026-10-08_pcm_pdx_implementation.md) を参照。
以下は実装前の調査記録であり、「未修正／未実装」はその時点の状態。

## 今回の依頼と状態

ユーザーの依頼は、添付 `C:/Users/ef110/Downloads/x68k_vgm2mml_pcm_pdx_codex_instruction.md` の検討と、将来のZ_MUSIC対応を踏まえた設計判断。今回は調査と設計提案までであり、PCM変換の実装開始は依頼されていない。添付のスキーマ・ツール名は候補として確認し、確定仕様とは扱わない。添付本文はリポジトリへ転載しない。

直前のPSG/SCC改善は公開の最低限チェック成功時点で中断中。今回、その実装や生成物は変更していない。前段の記録は `2026-10-08_psg_opm_musical_connection.md`。全無音入力の残件も維持する。

## 判断

添付案の中心である「生PCM情報 → 再生区間 → 完全一致のサンプル表 → MMLとPDX」は採用を提案する。追加すべき条件は次の通り。

1. DAC Stream Controlと直接OKIM6258書き込みの両方を、同じ物理チップの時刻・状態へ解決する。
2. バイト列の同一性と、開始状態を含む再生の同等性を別に検証する。
3. 共通 `sample_id` とターゲットのスロット番号を分ける。MDXのMMLとPDXだけが同一のターゲット対応表を共有する。
4. PCMとOPMが同じMDX時計・曲終端を使う。OPMだけで選んだ時計へPCMを後から付加しない。
5. PDX生成の外部ツール依存と、変換できない入力の診断を明示する。

マクロ、新規MDXコンパイラ、波形類似照合、WAV経由の通常再符号化、Z_MUSIC出力そのものは今回の最初の実装範囲に含めない。

## 現状のコード

| 境界 | 現状・変更点の候補 |
| --- | --- |
| Raw VGM | `py/vgm_timing.py:52` はデータブロック長を読み、同:67は0x90〜0x95の命令長を走査する。ペイロードをwaitと誤解しない共通時計を再利用できる。 |
| Reader / State | `py/vgm_reader.py:824` 以降はPSG/OPLL/OPM/SCCだけを解析。0x67・0x90〜0x95・0xB7のPCM情報は現在捨てられる。 |
| Header | `py/vgm_io.py` の版・data_startに従うフィールド読取を拡張する。OKIM6258 clockは0x90、optionsは0x94。 |
| 既存診断 | `scripts/verify_opm_mdx_roundtrip.py:35` は0x98をPCM clockとして読む。これはOKIM6295側であり、OKIM6258の有無判定には使えない。今回バグを確認、修正は未実施。 |
| Native orchestration | `py/opm_conversion.py:22` 以降はOPM不在で拒否。PCMのみ／OPM無音でも、架空のOPMイベントを作らずにMDXを構成する必要がある。 |
| 時計 | `py/opm_mdx_music.py:66` の時計候補検査はOPMの境界だけ。PCM開始・停止・速度・panなどの境界を候補検査へ加え、現行の6 VGM samples以内の目標を検査する。 |
| MDX組立 | 同:416 `render_music_tracks` はトラック単位の組立・既存ループ処理を再利用できる。PCM用unitとdumpは別途必要。既存 `MusicalMdx.dump` のtrajectoryや集計はOPM前提なので、そのままPCMをOPM stateに偽装しない。 |
| 既存外部helper | `scripts/mdx_fixture_generator/src/main.rs:48` 以降はPDX名・PCMノートを明示的に拒否。PDX読込・検証・再生を追加する必要がある。 |
| 聴き比べ出力 | `scripts/export_mdx.py` はMML/MDX/VGMの3ファイルを前提。PDXを追加し、今回の出力か・生成に失敗したかをresultsへ記録する必要がある。 |

SCCの `py/scc.py:97` 以降にある波形バイト列の完全一致によるID共有は参考になる。ただし、32-byte wavetableと可変長ADPCMでは再生状態が違うため、SCCの音符・波形切替ロジックまでは転用しない。

## VGMが保持するもの

[VGM 1.71仕様](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/vgmspec171.txt)を確認した。

- OKIM6258のバンク型は0x04。0x44は圧縮データブロックで、VGMの圧縮を解いた後のADPCMバイト列を扱う。これはADPCMの音声デコードとは別工程。
- 0x90は書込先、0x91はバンクとstep/base、0x92は書込頻度、0x93は開始位置と長さの解釈、0x94は停止、0x95はブロックIDによる再生を表す。
- バンクへのブロック追加と、一回の再生が消費する範囲は別。ブロック境界を自動的に楽器サンプルの境界にしない。
- ヘッダーのチップ時計・分周・モード、直接0xB7書き込みも保存する。

stream_idは転送制御の識別子で、音楽的声部や独立したPCMチャンネルを意味しない。同じOKIM6258へ書くストリームと直接書き込みは、時刻・命令順を保って同じチップ状態へ解決する。転送終了と音声終了も分ける。

[MAME OKIM6258実装](https://github.com/mamedev/mame/blob/master/src/devices/sound/okim6258.cpp)では、データ書き込みは入力値とnibble位置を更新し、再生中のpredictor/stepは継続する。再生へ移る制御でリセットされる。このエミュレーター実装は状態保持が必要な根拠であり、実機確認の代用とはしない。

## 手元の入力調査

本文・音声・ADPCM bytesを出力せず、命令数とヘッダーの数値だけを調べた限定調査。

- 公開 `opm/from_mdx` の9件は、0x67・0x90〜0x95・0xB7がすべて0件。PCM受入テストには使えない。
- ローカルOPMの代表5件中、KMSM009は0xB7が3,434,358件、OKIM6258 clock=8,000,000、options=2、宣言VGM loopなし。ほかの4件はPCM命令・clockなし。
- この例では0x93/0x95経路の証拠は得ていない。全コレクションの傾向とは断定しない。

したがって、実装開始時には直接0xB7のcontrol/data内訳、play/stop/resetの有無と順序を先に調べる。ストリーム型だけ対応して完了とはしない。数百万件の転送をすべて重複したstate objectに展開する設計も避け、生bytes・時刻の列と状態遷移／checkpointを分けてストリーミング処理する。dump可能なsource event ID、命令位置、転送履歴は残す。

## 共通PCM IRの提案

ここで挙げるフィールドとモジュール名は実装時に既存規約へ合わせる案。

```text
Raw VGM / blocks / B7 / stream commands
    -> OKIM6258 state + ordered transfer history
    -> playback segments + exact encoded sample table
    -> target binding
        -> MXDRV MML + PDX
        -> future Z_MUSIC MML + sample container
```

- **Raw**: event_id/address/source_vgmticks、chip_instance、block type/index、bank offset、元payload、stream命令と全operand。圧縮前ブロックと展開結果の関係も残す。
- **State**: chip clock/options/control/pan、stream位置・step/base・残量・loop/reverse、byte供給時計とnibble消費時計、reset状態とその根拠。未観測値はunknownにする。
- **Playback Segment**: start/endとその根拠、物理チップ、全source spans、実際に供給／消費されたbytesまたはnibbles、停止・切替・打切り、開始時のdecoder状態。音楽的区切りを音声類似性から捏造しない。
- **Canonical Sample**: 無制限の安定sample_id、codec、符号化bytes、長さ、hash、参照元の複数span。hash一致後もbyte equalityで確定。rate/pan/元ノート番号を勝手にサンプルの同一性へ混ぜない。
- **Playback Event**: sample_id、source start/end、rateの有理数、pan/control trajectory、source event IDs、reset/continuation属性。元の音楽的root noteが不明ならunknownのままにする。
- **Target Binding**: MDX側で一度だけsample_id→(bank,slot)を確定。MMLとPDXは同じimmutable bindingを使う。IRに96件制限やPトラックを埋め込まない。

バイト同一なら同じassetを参照できるが、それだけでPDXノートとして独立再生できるとは判定しない。範囲途中開始、nibble途中切断、resetなし継続、異常な転送間隔は別途適合性を判定する。表現できない場合もRaw/Stateを保存し、未変換を明示する。無音化して成功扱いにしない。

## MDX / PDX出力と既存ツール

既存固定版は `mmlx=0.2.0` と `soundlog=0.15.0`。ローカルCargoソースも読んだ。

- mmlxは `#pcmfile`、PCMトラックP〜W、数値ノートn0〜n95をコンパイルできる。ただしコンパイル時にはPDXを開かず、参照先の存在を保証しない。
- soundlogの `PdxBuilder` は既に符号化済みのbytesを受け取り、再エンコードせず、既定では非圧縮PDXを作る。96 slots/bank、空slot、BE offset/length table、順次配置を実装する。32 banks上限は当該ライブラリの制限であり、すべてのMXDRV版の仕様とはしない。
- `MdxPackage::parse(mdx, Some(pdx))` と `pcm_references()` は参照slot欠落を検出できる。ただし静的参照照合だけでは演奏時のループ・bank状態を証明しないため、実行履歴も調べる。
- [mdxtools](https://github.com/vampirefrog/mdxtools)には参照・デコード・ADPCMエンコード機能があるが、調査したREADMEとPDX資料ではraw ADPCM→PDXの構築CLIを確認できなかった。

**第一候補はsoundlog PdxBuilderを既存Rust helperの小さな追加モードから使う方式。** raw bytes不変、空slot、slot95、長さ・offsetの範囲を小規模実証してから採用を確定する。ライブラリが許す32-bit長さが対象MXDRVでも許されるとは仮定しない。アライメントを追加する処理は読んだ実装にはなく、対象プレイヤーで短い奇数長サンプルも確認する。

この方式ではPCM/PDX出力にビルド済みhelperが必要になる。OPM-only変換のPython依存は現状のまま維持する。helper不在なら依存不足を明示し、PDX欠落を正常完了として返さない。Pythonだけで完結させる選択を後で行う場合も、PDX writerをターゲット層の限定機能として差し替えればよい。

最初のMDX backend範囲は標準4-bit OKIM6258 ADPCM、単一物理PCMチャンネル、単一PDX bank（96 slots）。超過・別モードは検出して診断する。これは初期スコープであり、最終的なネイティブ対応の完了範囲ではない。

OPMの時計選択にPCMの開始・停止・rate/pan変更・曲終端を加える。元VGM clock、stream byte frequency、ADPCM nibble sample rate、MDX F設定は別の量として記録する。任意のstream HzをMDXの離散F値へ無報告で丸めない。PCM-onlyでは必要なtempoトラックを生成できても、架空のOPM発音／voice／source stateを作らない。

参照した固定版ソース:
`/home/emef220/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/`
以下の `soundlog-0.15.0/src/mdx/pdx.rs`（PdxBuilder）、
`package.rs`（参照解決）、`mmlx-0.2.0/src/mdx/compile.rs`（PCM編訳）。

## Z_MUSICを見据える境界

[Z-MUSIC v2原マニュアル MEASURE12](https://github.com/kg68k/zmusic2/blob/main/manual/zm12.txt)ではZPDはnote番号と相対offset・長さの表を持つ。PDXの96slot表とは異なる。
[Z-MUSIC v3原マニュアル MEASURE15](https://github.com/kg68k/zmusic3/blob/main/manual/zm15.txt)ではMPCMがADPCMとsigned 8/16-bit PCMを扱い、元ノート・loop情報も使う。

よって共通IRにはcodec、source ranges、実再生rate、loop/reset/continuationの証拠を残し、将来Z_MUSIC側でその版・driverに適した対応表を作る。PDXを共通データ形式にしない。今回ZPD writer、ZMS生成、Z-MUSIC用のコンパイラ選定は実装しない。将来のversion選択が共通IRの設計を妨げる状態にもさせない。

OPMのRaw/State/Segmentsも将来の入力にできる。ただし現行MDX用MusicUnitにはMML commandが含まれるので、そのMMLをZMSへ文字置換して共通化する設計は採らない。必要な共通化はZ backend着手時に、音楽構造とtarget文字列の境界で行う。

## 復元できる範囲と限界

- 再生対象bytes、順序、時計、resetの証拠が揃う場合、元PDXのslot番号を回復せずとも、生成MDX→生成PDX→正しいbytesという関係を作れる。
- 途中開始やreset不明のADPCM、任意rate／転送間隔、チップモード不一致は標準PDXの独立ノートへそのまま移せるとは限らない。
- PCM8等でソフトウェア合成された結果をVGMが記録している場合、元の個別声部・元PDXのサンプル表は復元できないことがある。合成後の観測列と、元の楽器サンプルを区別する。
- データ欠落／範囲外参照／切れたファイルは診断する。参照MDX/PDXで勝手に埋めて通常変換の成功にしない。
- VGMのsong loopでADPCM状態が継続する場合、MDX loopが新しいサンプル開始を作るかも別に検証する。

## 実装順序と受け入れテスト

1. **ヘッダーと入力形式の把握**: 0x90/0x94の版・data_start境界、既存PCM有無診断の修正。直接B7とstreamの共通Raw記録。実入力のreset/control調査。
2. **公開の短いPCM入力**: 手作成の短いADPCM bytesと既知の開始/停止/データ命令列。直接B7を初期の必須経路として、decoder状態とbyte/nibble時刻を検証する。OPM+PCMとPCM-onlyの両方を作る。
3. **完全一致サンプル表とPDX小規模実証**: 同一bytesの再利用、異なる開始状態の非同等、空slot/最大slot/slot範囲超過、offset/長さ境界、payload不変を独立の期待値で検査。PDX tool選定を確定する。
4. **MDX PCMトラックの接続**: 同一bindingから#pcmfile・PトラックとPDX生成。mmlx compile、全参照解決、soundlogによる演奏履歴・再生rate/start/stop/panの検査。OPM-only出力不変も検査。
5. **stream・構造の拡充**: 0x93範囲と0x95 block、バンク連結、step/base、長さmode、stop/retrigger、loop/reverse、圧縮44。対応前でも未対応を明示し、Raw保存を検証する。
6. **既存MDX+PDXのローカル参照**: 使用可能な資料を改変せず、PDX bytesとVGM由来bytes・PCM選択の意味を比較。最後にMMDSP等で聴感・GUI確認。私有fixtureと生成曲はgitへ入れない。

境界テストには同時刻のstop/play/data順、PCM終了がOPMより後、OPM無音、PCM時計がOPM-only時計では潰れる例、曲loopの状態継続、PDX欠落を含める。抽出器自身を唯一のoracleにせず、手作成期待値と独立PDX/MDX解析で照合する。

最初の受け入れ基準は「既存コンパイラで生成したMDXとPDXの全PCM参照が有効で、対応する符号化bytesと許容範囲内の再生条件が確認できること」。単なるコンパイル成功、サンプル件数一致、音が出ることだけで完了とはしない。

## 今回行った検証

コード・固定版依存・一次資料の読取、上記限定メタデータ調査、設計のarchitectレビューを実施。変換挙動は変更していないため新しい自動テスト／PCM往復検証／PDX生成実証は未実施。以上は実装済みの仕様書ではなく、次の作業に使う検討結果。
