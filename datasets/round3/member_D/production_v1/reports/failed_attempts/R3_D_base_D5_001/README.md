# R3_D_base_D5_001 first attempt

The first attempt at 8-worker concurrency failed during full physical replay with `MemoryError` after 36/42 spectra. Sealed data and QC were not deleted; they were moved aside to preserve the failure evidence and the batch was regenerated from the frozen batch definition under 4-worker concurrency. The delivered archive is the successful rerun; its SHA-256 is in archive_index.json. No window budget was loosened and no spectrum was dropped.
