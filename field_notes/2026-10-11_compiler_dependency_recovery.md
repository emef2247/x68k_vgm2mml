# Compiler dependencies removed with outputs

The user exported NEMESIS successfully, deleted `outputs/`, then observed
`compilation_failed`. Their saved error log states `Missing --mxc tool`.
MML generation succeeded. Default MXC and run68 discovery had depended on
`outputs/research/`; deleting generated data therefore removed dependencies.
This is a dependency-layout defect, not evidence of a normalization regression.

Default persistent locations are now `.tools/mxc/mxc.x` and
`.tools/run68x/build/run68`. Explicit options and PATH retain priority; legacy
paths remain a last fallback for existing installations. Missing-tool errors
point to `docs/mdx_compiler_setup.md`. `.tools/` is ignored by Git.

Restored local dependencies match the recorded baseline: MXC archive SHA256
`4d4a6f00a100c728f5f4b217998e66ca8e6fa530cdfe1a5ee7c03f70715d98c4`,
compiler SHA256
`38def25dae39ae35a16668f086843ae9f0d00295e50fd034b7b4108f7c762086`,
run68x revision `fc28826dd795b1f0a3241f0b03fe2353e12e7233`.
The archive requires an LH1-capable decoder; Python lhafile cannot decode it.
For this recovery Ubuntu lhasa 0.3.1-4 packages were extracted locally without
changing the system installation.

Validation: all 18 compiler-adapter tests passed, including compilation using
the persistent paths with no `outputs/` directory, persistent-path priority,
legacy fallback and rejection of an invalid explicit override. One public
`opm/from_fm/block_boundary` export with default options succeeded through
MXC compilation, binary validation and MDX-to-VGM replay. Artifacts are under
ignored `outputs/compiler_recovery_public/`. No local_only conversion, broad
regression or native GUI test was run. Source IR, target timing and MML syntax
are unchanged by this fix.
