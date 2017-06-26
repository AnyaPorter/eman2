#!/usr/bin/env bash

source ci_support/pre_build.sh

cmake $src_dir -DENABLE_CONDA=ON
make
make install
make test-verbose

export PREFIX=$CONDA_PREFIX
export SP_DIR=$(python -c "import site; print site.getsitepackages()[0]")

source $src_dir/ci_support/post_build.sh
