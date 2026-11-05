# MDXコンパイラのセットアップ（WSL）

試聴用エクスポートおよびOPMの往復検証では、既定でmmlxを使用します。型付きPCMバックエンドでも、FM部分にはmmlxを使用します。run68経由で本来のMXCを使ってコンパイルする場合は、`--compiler mxc` を明示的に指定してください。

外部ツールは、生成物を格納する `outputs/` ではなく、Gitの管理対象から除外された `.tools/` に配置します。`outputs/` を削除しても依存ツールが失われないようにするためです。

ツールの検索順序は、明示指定された `--mxc` / `--run68`、PATH、`.tools/`、最後に互換性維持のための旧 `outputs/research/` 配下です。明示指定されたパスが無効な場合はエラーとし、別のコンパイラへ暗黙に切り替えることはありません。

## コマンドによる一括セットアップ

WSL上で実行してください。スクリプトは自身の配置場所からリポジトリを特定します。

```sh
bash scripts/setup_tools.sh
# 調査用の独立したメタデータ解析・逆コンパイルツールもインストールする場合：
bash scripts/setup_tools.sh --with-mdxtools
# ZMDの再生確認用にZMUSICのプログラムもインストールする場合：
bash scripts/setup_tools.sh --with-zmusic
```

標準のセットアップでは、MXC v1.01、リビジョンを固定したrun68x、および `cargo build --release --locked` でビルドするRust製ヘルパー（mmlx 0.2.0 / soundlog 0.15.0）を導入します。

オプションの構成では、固定リビジョン `9c8539fec2757fcf7c85d1986171b50ebe2ef1e5` のmdxtoolsと、その固定されたサブモジュールから、`mdxinfo`、`pdxinfo`、`mdxdump`、`mdx2mml` をビルドします。実行ファイルは `.tools/mdxtools/` に配置されます。使用例：

```sh
.tools/mdxtools/mdxinfo -u -H path/to/score.mdx
```

ZMUSIC用の構成では、固定リビジョン `ce859733704fa99fc1219488ad6f0c905261765f` のzmusic3チェックアウトに同梱された配布アーカイブから、ZMUSIC 3.02Cのプログラム `ZMSC3.X`、`ZMC.X`、`ZP3.R` を `.tools/zmusic/` へ展開します。変換ツールはZMDを直接生成し、これらのプログラムを実行することはありません。X68000側での再生確認（上記のrun68x経由など）のための環境です。

必要な環境は、Python 3.10以降、Rust 2024 Editionに対応したRust/Cargo（Rust 1.85以降）、git、curl、CMake、make、Cコンパイラ、sha256sumです。MXCまたはZMUSICを新規に展開する場合は、Ubuntuの `lhasa`（またはLH1形式に対応した別の `lha`）も必要です。Ubuntu/WSLでは、以下のように導入できます。

```sh
sudo apt-get update
sudo apt-get install build-essential cmake git curl python3 lhasa
```

Rust/Cargoは、普段使用しているRustツールチェーンの導入方法で、スクリプト実行前にインストールしてください。CargoがPATHに存在しない場合は、`$HOME/.cargo/bin` も検索します。

このスクリプトは `sudo` を実行せず、パッケージをシステム全体にインストールすることもありません。前提ツールが不足している場合は、対処方法を示して停止します。既存のソース変更や、ハッシュ値の異なるMXCは上書きせず、状況を報告します。

同じコマンドを再実行すると、環境の検証・再ビルドを行えます。MXCのアーカイブとコンパイラのハッシュ値、およびGitリビジョンは固定されており、Cargoの依存関係は `Cargo.lock` で固定されています。

`.tools/setup_manifest.json` には、インストールした実行ファイルのハッシュ値、リビジョン、およびロックファイルのハッシュ値を記録します。ローカルでビルドしたバイナリのハッシュ値はホストのコンパイラによって異なる場合があるため、再現性は同じソースと依存関係のバージョンによって確保します。

調査用のオプション構成は、過去の実験結果を再生成したり、無関係なプレイヤー、ファームウェア、エミュレータ環境をインストールしたりするものではありません。

## 手動セットアップ

以下の手順では、2026年10月9日に検証した基準環境と同じコンパイラおよび実行環境のリビジョンを使用します。WSL上で、リポジトリのルートディレクトリから実行してください。

必要なものはPython 3、curl、git、CMake、Cコンパイラ、および `-lh1-` 形式に対応するLHA展開ツール（Ubuntuでは `lhasa` パッケージ）です。このアーカイブにはPythonの `lhafile` を使用しないでください。該当する圧縮形式に対応していません。

MXCのアーカイブは、[mdxtoolsのコンパイル手順](https://github.com/vampirefrog/mdxtools/blob/master/README.md)でも案内されています。MXC v1.01には、MFS soft / milk、1989年の表記があります。ツールの実行ファイルはローカルの依存物として扱い、リポジトリにコミットしたり、試聴用の出力パッケージにコピーしたりしません。

```sh
mkdir -p .tools/mxc
curl -fL https://nfggames.com/x68000/Mirrors/x68pub/x68tools/SOUND/MXDRV/MDX_TOOL.lzh \
  -o .tools/mxc/MDX_TOOL.lzh
printf '%s  %s\n' \
  4d4a6f00a100c728f5f4b217998e66ca8e6fa530cdfe1a5ee7c03f70715d98c4 \
  .tools/mxc/MDX_TOOL.lzh | sha256sum -c -
# チェックサムの検証に成功した場合のみ続行してください。
(cd .tools/mxc && lha x MDX_TOOL.lzh mxc.x mxc.doc)
printf '%s  %s\n' \
  38def25dae39ae35a16668f086843ae9f0d00295e50fd034b7b4108f7c762086 \
  .tools/mxc/mxc.x | sha256sum -c -

# cloneは初回のみ実行してください。インストール済みの場合は省略します。
git clone https://github.com/kg68k/run68x.git .tools/run68x
git -C .tools/run68x checkout --detach fc28826dd795b1f0a3241f0b03fe2353e12e7233
cmake -S .tools/run68x -B .tools/run68x/build \
  -DCMAKE_C_FLAGS=-Wno-error=format-truncation
cmake --build .tools/run68x/build -j2
```

GCC 11向けの警告オプションは従来の基準環境に合わせたもので、エミュレータのソースコードを変更するものではありません。Rust製ヘルパーは別の依存物であり、こちらも `outputs/` の外に配置します。

```sh
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python3 scripts/export_mdx.py tests/fixtures/public/opm/from_fm/block_boundary/ \
  --outdir outputs/compiler_smoke
```

セットアップ後は、通常のエクスポートコマンドでツールのパスを指定する必要はありません。必要に応じて、`--mxc /persistent/path/MXC.X --run68 /persistent/path/run68` のように明示指定することもできます。

PCMには既存の型付きPCMバックエンドを使用します。このセットアップによってPCMの処理経路が変更されることはありません。

## 類似したSegaPCMサンプルの共有

既定の `--pcm-bank-merge budget96` によるPCMターゲット処理では、NumPyを使用します。

```sh
python3 -m pip install numpy
```

SciPyや新たな音源エミュレータは不要です。完全に同一のバイト列だけを共有する方式と比較する場合は、`--pcm-bank-merge off` を指定してください。

この方針は、対象となるMSM6258、Delta-T、SegaPCMのターゲット用データに適用されます。PSGのPCM抽出は別の処理です。詳細は[PCMバンクの削減](pcm_bank_reduction.md)を参照してください。

## ツールのライセンスと再配布

固定したバージョン、確認済みの著作権・ライセンス表示、および配布対象の範囲については、[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)を参照してください。

MXCのフリーウェアとしての利用許諾は `.tools/mxc/mxc.doc` に記載されています。run68xはGPL v2以降、オプションのmdxtoolsはGPL v3です。これらはローカルで取得・ビルドする外部ツールであり、試聴用の出力パッケージには同梱しません。元のドキュメントとソースコードのチェックアウトを保持してください。

Rust製ヘルパーはMITライセンスのmmlx/soundlogをリンクしています。バイナリを再配布する場合は、該当する間接依存ライブラリについても必要なライセンス表示を付ける必要があります。
