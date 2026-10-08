/* SPDX-License-Identifier: MIT */
/* Copyright (C) 2026 buberlo */
#ifndef APS5_GPU_PROBE_H
#define APS5_GPU_PROBE_H
#include <stdio.h>
/* Writes JSON Lines; zero means every executed test passed. No presentation
 * claim is made by this offscreen probe. Shader files live in shader_dir. */
int aps5_gpu_probe_run(const char *shader_dir, FILE *report);
#endif
