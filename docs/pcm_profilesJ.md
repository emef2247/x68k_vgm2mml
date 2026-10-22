# PCM出力の容量・音質プロファイル

`vgm2mml.py`と`scripts/export_mdx.py`に`--pcm-profile standard|low|ultra_low`を指定できる。
既定は`standard`で、従来の符号化バイト・レート選択を維持する。low／ultra_lowは出力側だけの
レート削減・再符号化であり、元のState／Segment／PCM IRを上書きしない。

```sh
python scripts/export_mdx.py INPUT --outdir outputs/pcm_ultra_low \
  --no-vgm --compiler mmlx --pcm-policy best-effort --pcm-profile ultra_low
```

既存の`--force`や`--no-song-loop`と併用できる。low／ultra_lowによる既知の音質損失も
`best-effort`の対象であり、容量や未対応制御を無条件に許可するオプションではない。

| source経路 | standard | low | ultra_low |
|---|---|---|---|
| SegaPCM／連続Delta-Tの派生波形 | 15625 Hz（F4）、最大8秒包装 | 7812.5 Hz（F2）、最大16秒包装 | 3906.25 Hz（F0）、最大32秒包装 |
| 独立Delta-T | 元rateに近いF0..F4へ再符号化 | F0..F2の範囲で元rateに近い値へ再符号化 | F0へ再符号化 |
| native MSM6258 | 従来どおり符号化バイトを保持 | F0..F2の範囲へ再符号化。既に上限以下の標準rateならバイト列を保持 | F0へ再符号化。既にF0ならバイト列を保持 |

F0..F2は3906.25、15625/3、7812.5 Hz。対象rateに合わせて符号化sample数と
MDXのF命令を変更し、遅い速度で再生するのではなく元の音程・時間を保つ。
F0は4 MHz／1024、F2は8 MHz／1024である。profileに保存した実クロックと
dividerも派生PCM IR／bridgeへ反映し、レートとF命令を一致させる。
偶数sample数（最少2）への丸め、共有MDX clockへの境界補正、符号化誤差は診断する。
派生波形の最終clockアラインも選択profileのrateで再符号化する。
独立sampleの自然終了とgate時刻が完全に一致する保証は従来どおり別問題となる。

## 効果と制約

15.6 kHzから7.8 kHzへの変換では、同じ時間の音声データはおおむね半分になる。
ultra_lowの3.9 kHzでは標準のおおむね1/4となる。
長い派生波形は少ない包装サンプルへまとめられるため、96枠制限にも効く場合がある。
ただし、無音・元の発音区間・曲ループ境界は保持するので、すべての入力で枠数が
半減するわけではない。バイト一致の重複排除、丸め、force省略により結果も変わる。
既に低rateのMSMやDelta-Tは削減されないことがある。

lowの16秒包装・ultra_lowの32秒包装はstandardの8秒包装と最大音声ペイロードが同程度（約62500 bytes）。
総バンク容量／サンプル数の削減を目的とし、単一サンプルの最大バッファ要求を
下げるものではない。独立Delta-T／native MSMはこの包装分割と別経路であり、
低レート化後も検証済みのsample容量範囲を超えれば従来の拒否／force省略対象となる。
プレイヤーのPCMバッファ上限やメモリ配置へ必ず収まるとは
保証しない。PDXの96枠・現在検証済みの65535-byte/sample範囲は変更しない。

元のPCMが持つ高域は失われ、既存の線形補間には専用アンチエイリアスフィルタが
ないため折り返しもあり得る。ADPCMの再符号化誤差、10-bit出力、包装境界ごとの
独立predictor仮定も残る。音質と視聴結果は実データで比較する。

MSM6258のreset／供給cadence／未対応モード等のsourceガードは維持する。
low／ultra_lowは未知のdecoder状態や入力破損を解消しない。既に低rateで無変更の場合には
再符号化lossを捏造せず、実際に変換したplaybackだけにsource時刻付きのlossを残す。

## 中間結果

- native MSMの`.pcm_*`、SegaPCM、Delta-Tの元IRは保持する。
- native MSMの派生データは`.pcm_low.pcm_*`／`.pcm_ultra_low.pcm_*`へ分け、`.pcm_profile.json`／
  `.pcm_profile.mapping.csv`に元／出力rate・byte数・ID・時刻・誤差・再符号化数を保存する。
- 派生波形の`.*_pcm_bridge.json`／mappingにはprofile、正確な分数rate、F番号、
  最大包装秒数と出力byte数を保存する。独立Delta-Tは`.opna_pcm_bridge.json`も参照する。
- `.pcm.timing.json`の`pcm_profile`／`pcm_payload_bytes`は最終採用結果。
  PDXヘッダーと音声ペイロードの容量は区別する。TXTにも選択profileを表示する。
- 通常CLIの`.conversion.json`の`pcm_options`には要求profileと適用可能性を記録する。

mucom88側のMSM6258／SegaPCMにも同名profileを実装しているが、ターゲットは
YM2608のADPCM-Bバンクである。整数Delta-Nから実rateを求めてMUCへ反映し、
32枠・256 KiBペイロード・整列制約を適用する。PDXの制約と混同しない。
mucom88のネイティブOPNA ADPCM-Bは元のbyte／rateを保つ別経路で、今回は対象外。

## 一括変換の待ち時間

`scripts/export_mdx.py`の既定タイムアウトは各入力・各段階につき600秒。
明示的な`--timeout`は優先される。再生時間やPCM容量の上限を指定する値ではない。
低レート化してもnative波形の解析量そのものは減らないため、処理時間が1/4になる保証はない。
