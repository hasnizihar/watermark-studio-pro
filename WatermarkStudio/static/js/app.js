// Watermark Studio Pro V2 - Frontend Application Controller
document.addEventListener('DOMContentLoaded', () => {
    // Application State
    let scannedImages = [];
    let plannedMap = new Map();
    let selectedImage = null;
    let selectedImageSet = new Set();
    let currentFilter = 'all';
    let currentSort = 'name_asc';
    let currentSearch = '';
    let currentView = 'grid'; // 'grid' or 'list'
    let pollInterval = null;
    let previewDebounceTimer = null;
    let zoomScale = 1.0;
    let isSliderDragging = false;

    // DOM Elements - Topbar
    const statTotal = document.getElementById('statTotal');
    const statPortrait = document.getElementById('statPortrait');
    const statLandscape = document.getElementById('statLandscape');
    const statSquare = document.getElementById('statSquare');
    const btnOpenOutputTop = document.getElementById('btnOpenOutputTop');

    // DOM Elements - Sidebar
    const inputDirInput = document.getElementById('inputDir');
    const outputDirInput = document.getElementById('outputDir');
    const wmVertPathInput = document.getElementById('wmVertPath');
    const wmHorizPathInput = document.getElementById('wmHorizPath');
    const presetSelect = document.getElementById('presetSelect');
    const opacitySlider = document.getElementById('opacitySlider');
    const opacityVal = document.getElementById('opacityVal');
    const customPlacementBox = document.getElementById('customPlacementBox');
    const hAlignSelect = document.getElementById('hAlignSelect');
    const vAlignSelect = document.getElementById('vAlignSelect');
    const scaleSlider = document.getElementById('scaleSlider');
    const scaleVal = document.getElementById('scaleVal');
    const namingPrefixInput = document.getElementById('namingPrefix');
    const startIndexInput = document.getElementById('startIndex');
    const padDigitsInput = document.getElementById('padDigits');
    const outputStructure = document.getElementById('outputStructure');
    const overwriteExisting = document.getElementById('overwriteExisting');
    const namingPreview = document.getElementById('namingPreview');
    const btnScan = document.getElementById('btnScan');

    // DOM Elements - Workspace
    const btnViewGrid = document.getElementById('btnViewGrid');
    const btnViewList = document.getElementById('btnViewList');
    const photoGrid = document.getElementById('photoGrid');
    const photoList = document.getElementById('photoList');
    const tableBody = document.getElementById('tableBody');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const searchInput = document.getElementById('searchInput');
    const sortSelect = document.getElementById('sortSelect');
    const pillCountAll = document.getElementById('pillCountAll');
    const pillCountPortrait = document.getElementById('pillCountPortrait');
    const pillCountLandscape = document.getElementById('pillCountLandscape');

    // DOM Elements - Preview Panel
    const previewEmptyBox = document.getElementById('previewEmptyBox');
    const sliderComparison = document.getElementById('sliderComparison');
    const compWrapper = document.getElementById('compWrapper');
    const compImgOriginal = document.getElementById('compImgOriginal');
    const compImgWatermarked = document.getElementById('compImgWatermarked');
    const compOverlayClip = document.getElementById('compOverlayClip');
    const sliderHandle = document.getElementById('sliderHandle');
    const btnZoomOut = document.getElementById('btnZoomOut');
    const btnZoomIn = document.getElementById('btnZoomIn');
    const btnZoomFit = document.getElementById('btnZoomFit');
    const zoomLevelText = document.getElementById('zoomLevelText');

    const metaFilename = document.getElementById('metaFilename');
    const metaResolution = document.getElementById('metaResolution');
    const metaOrientationSelect = document.getElementById('metaOrientationSelect');
    const metaWatermark = document.getElementById('metaWatermark');
    const metaExportName = document.getElementById('metaExportName');

    // DOM Elements - Bottom Panel
    const btnStartBatch = document.getElementById('btnStartBatch');
    const btnPauseBatch = document.getElementById('btnPauseBatch');
    const btnCancelBatch = document.getElementById('btnCancelBatch');
    const btnOpenCompleted = document.getElementById('btnOpenCompleted');
    const jobStatusText = document.getElementById('jobStatusText');
    const jobCountText = document.getElementById('jobCountText');
    const jobPercentText = document.getElementById('jobPercentText');
    const jobProgressFill = document.getElementById('jobProgressFill');
    const btnToggleLogs = document.getElementById('btnToggleLogs');
    const logDrawer = document.getElementById('logDrawer');
    const logTerminal = document.getElementById('logTerminal');
    const btnCloseLog = document.getElementById('btnCloseLog');

    // 1. Initialize & Fetch Settings
    fetch('/api/settings')
        .then(res => res.json())
        .then(data => {
            const s = data.settings || {};
            if (s.input_dir) inputDirInput.value = s.input_dir;
            if (s.output_dir) outputDirInput.value = s.output_dir;
            if (s.wm_vert_path) wmVertPathInput.value = s.wm_vert_path;
            if (s.wm_horiz_path) wmHorizPathInput.value = s.wm_horiz_path;
            if (s.naming_prefix) namingPrefixInput.value = s.naming_prefix;
            if (s.start_index) startIndexInput.value = s.start_index;
            if (s.pad_digits) padDigitsInput.value = s.pad_digits;
            if (s.placement_mode) presetSelect.value = s.placement_mode;
            if (s.opacity !== undefined) {
                opacitySlider.value = s.opacity;
                opacityVal.textContent = `${Math.round(s.opacity * 100)}%`;
            }
            if (s.output_structure) outputStructure.value = s.output_structure;
            if (s.overwrite_existing !== undefined) overwriteExisting.checked = s.overwrite_existing;

            togglePlacementControls();
            updateNamingPreview();

            if (s.input_dir) {
                scanImages();
            }
        })
        .catch(err => console.error("Error loading settings:", err));

    // 2. Native Windows Browse Buttons
    document.querySelectorAll('.btn-browse').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const type = btn.getAttribute('data-browse');
            const targetId = btn.getAttribute('data-target');
            const targetInput = document.getElementById(targetId);

            try {
                showToast("Opening Windows File Picker...", "info");
                const res = await fetch('/api/browse', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        type: type === 'dir' ? 'directory' : 'file',
                        initial_dir: targetInput.value || ''
                    })
                });
                const data = await res.json();
                if (data.success && data.path) {
                    targetInput.value = data.path;
                    showToast("Path updated", "success");
                    saveCurrentSettings();
                    if (targetId === 'inputDir') {
                        scanImages();
                    } else {
                        triggerDebouncedPreview();
                    }
                }
            } catch (err) {
                showToast("Error opening file picker", "error");
            }
        });
    });

    // 3. Scan & Import Images
    async function scanImages() {
        const inputDir = inputDirInput.value.trim();
        if (!inputDir) {
            showToast("Please select a source folder", "error");
            return;
        }

        btnScan.disabled = true;
        btnScan.innerHTML = `<span class="spinner"></span> Scanning...`;
        jobStatusText.textContent = "Scanning directory and reading metadata...";

        try {
            const res = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    input_dir: inputDir,
                    output_dir: outputDirInput.value.trim()
                })
            });
            const data = await res.json();

            if (!data.success) {
                showToast(data.error || "Failed to scan folder", "error");
                jobStatusText.textContent = "Error scanning folder.";
                btnScan.disabled = false;
                btnScan.textContent = "Scan / Refresh Gallery";
                return;
            }

            scannedImages = data.images || [];
            selectedImageSet = new Set(scannedImages.map(img => img.abs_path));
            selectAllCheckbox.checked = true;

            // Update stats
            statTotal.textContent = data.total;
            statPortrait.textContent = data.portrait_count;
            statLandscape.textContent = data.landscape_count;
            statSquare.textContent = data.square_count || 0;

            pillCountAll.textContent = data.total;
            pillCountPortrait.textContent = data.portrait_count;
            pillCountLandscape.textContent = data.landscape_count;

            jobStatusText.textContent = `Found ${data.total} photos (${data.portrait_count} Portrait, ${data.landscape_count} Landscape)`;
            btnStartBatch.disabled = data.total === 0;

            await updatePlannedNames();
            renderWorkspace();

            if (scannedImages.length > 0) {
                selectPhoto(scannedImages[0]);
            }

            showToast(`Imported ${data.total} images`, "success");
        } catch (err) {
            showToast("Error communicating with server", "error");
        } finally {
            btnScan.disabled = false;
            btnScan.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"/>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                Scan / Refresh Gallery
            `;
        }
    }

    btnScan.addEventListener('click', scanImages);

    // 4. Update Planned Output Filenames
    async function updatePlannedNames() {
        if (scannedImages.length === 0) return;

        const config = getActiveConfig();
        try {
            const res = await fetch('/api/plan-names', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    images: scannedImages,
                    config: config
                })
            });
            const data = await res.json();
            if (data.success && data.planned) {
                plannedMap.clear();
                data.planned.forEach(item => {
                    plannedMap.set(item.abs_path, item);
                });
                updateNamingPreview();
            }
        } catch (err) {
            console.error("Error planning filenames:", err);
        }
    }

    function updateNamingPreview() {
        const prefix = namingPrefixInput.value.trim() || 'IMG_';
        const start = parseInt(startIndexInput.value) || 1;
        const pad = parseInt(padDigitsInput.value) || 2;
        const sampleNum = String(start).padStart(pad, '0');
        namingPreview.textContent = `${prefix}${sampleNum}.jpg`;

        if (selectedImage) {
            const planned = plannedMap.get(selectedImage.abs_path);
            if (planned) {
                metaExportName.textContent = planned.target_filename;
            }
        }
    }

    function getActiveConfig() {
        return {
            input_dir: inputDirInput.value.trim(),
            output_dir: outputDirInput.value.trim(),
            wm_vert_path: wmVertPathInput.value.trim(),
            wm_horiz_path: wmHorizPathInput.value.trim(),
            placement_mode: presetSelect.value,
            opacity: parseFloat(opacitySlider.value) || 1.0,
            horizontal_align: hAlignSelect.value,
            vertical_align: vAlignSelect.value,
            custom_scale: parseFloat(scaleSlider.value) || 0.3,
            naming_prefix: namingPrefixInput.value.trim(),
            start_index: parseInt(startIndexInput.value) || 1,
            pad_digits: parseInt(padDigitsInput.value) || 2,
            numbering_mode: document.querySelector('input[name="numberingMode"]:checked')?.value || 'sequential_all',
            output_structure: outputStructure.value,
            overwrite_existing: overwriteExisting.checked,
            export_format: "JPEG",
            jpeg_quality: 95
        };
    }

    function saveCurrentSettings() {
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getActiveConfig())
        }).catch(err => console.error("Could not save settings:", err));
    }

    // 5. Preset & Placement Controls
    function togglePlacementControls() {
        const mode = presetSelect.value;
        customPlacementBox.style.display = mode === 'custom' ? 'block' : 'none';
    }

    presetSelect.addEventListener('change', () => {
        togglePlacementControls();
        triggerDebouncedPreview();
        saveCurrentSettings();
    });

    opacitySlider.addEventListener('input', () => {
        opacityVal.textContent = `${Math.round(opacitySlider.value * 100)}%`;
        triggerDebouncedPreview();
    });

    scaleSlider.addEventListener('input', () => {
        scaleVal.textContent = `${Math.round(scaleSlider.value * 100)}%`;
        triggerDebouncedPreview();
    });

    [hAlignSelect, vAlignSelect].forEach(el => {
        el.addEventListener('change', () => {
            triggerDebouncedPreview();
            saveCurrentSettings();
        });
    });

    [namingPrefixInput, startIndexInput, padDigitsInput, outputStructure, overwriteExisting].forEach(el => {
        el.addEventListener('input', async () => {
            await updatePlannedNames();
            renderWorkspace();
            saveCurrentSettings();
        });
    });

    document.querySelectorAll('input[name="numberingMode"]').forEach(radio => {
        radio.addEventListener('change', async () => {
            await updatePlannedNames();
            renderWorkspace();
            saveCurrentSettings();
        });
    });

    // 6. View Mode Toggles & Search/Filter
    btnViewGrid.addEventListener('click', () => {
        currentView = 'grid';
        btnViewGrid.classList.add('active');
        btnViewList.classList.remove('active');
        photoGrid.style.display = 'grid';
        photoList.style.display = 'none';
        renderWorkspace();
    });

    btnViewList.addEventListener('click', () => {
        currentView = 'list';
        btnViewList.classList.add('active');
        btnViewGrid.classList.remove('active');
        photoGrid.style.display = 'none';
        photoList.style.display = 'block';
        renderWorkspace();
    });

    document.querySelectorAll('.filter-pills .pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.filter-pills .pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            currentFilter = pill.getAttribute('data-filter');
            renderWorkspace();
        });
    });

    searchInput.addEventListener('input', (e) => {
        currentSearch = e.target.value.toLowerCase().trim();
        renderWorkspace();
    });

    sortSelect.addEventListener('change', (e) => {
        currentSort = e.target.value;
        renderWorkspace();
    });

    // 7. Render Workspace (Grid or List)
    function renderWorkspace() {
        let filtered = scannedImages.filter(img => {
            if (currentFilter !== 'all' && img.orientation !== currentFilter) return false;
            if (currentSearch && !img.name.toLowerCase().includes(currentSearch)) return false;
            return true;
        });

        // Sort items
        filtered.sort((a, b) => {
            if (currentSort === 'name_asc') return a.name.localeCompare(b.name);
            if (currentSort === 'name_desc') return b.name.localeCompare(a.name);
            if (currentSort === 'orient') return a.orientation.localeCompare(b.orientation);
            if (currentSort === 'size') return b.size_bytes - a.size_bytes;
            return 0;
        });

        if (currentView === 'grid') {
            renderGrid(filtered);
        } else {
            renderList(filtered);
        }
    }

    function renderGrid(images) {
        photoGrid.innerHTML = '';
        if (images.length === 0) {
            photoGrid.innerHTML = `<div class="empty-placeholder"><p>No photos match the filter.</p></div>`;
            return;
        }

        images.forEach(img => {
            const planned = plannedMap.get(img.abs_path);
            const isSelected = selectedImage && selectedImage.abs_path === img.abs_path;
            const isChecked = selectedImageSet.has(img.abs_path);

            const card = document.createElement('div');
            card.className = `photo-card ${isSelected ? 'selected' : ''}`;
            const badgeClass = img.orientation === 'portrait' ? 'badge-p' : (img.orientation === 'landscape' ? 'badge-l' : 'badge-s');

            card.innerHTML = `
                <div class="card-thumb-wrap">
                    <img src="/api/thumbnail?path=${encodeURIComponent(img.abs_path)}" alt="${img.name}" loading="lazy">
                    <span class="card-orient-badge ${badgeClass}">${img.orientation.toUpperCase()[0]}</span>
                    <input type="checkbox" class="card-checkbox" ${isChecked ? 'checked' : ''}>
                </div>
                <div class="card-info">
                    <span class="card-title" title="${img.name}">${img.name}</span>
                    <span class="card-dim">${img.width}×${img.height}</span>
                </div>
            `;

            card.addEventListener('click', (e) => {
                if (e.target.classList.contains('card-checkbox')) return;
                selectPhoto(img);
            });

            const chk = card.querySelector('.card-checkbox');
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectedImageSet.add(img.abs_path);
                } else {
                    selectedImageSet.delete(img.abs_path);
                }
            });

            photoGrid.appendChild(card);
        });
    }

    function renderList(images) {
        tableBody.innerHTML = '';
        if (images.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="empty-cell">No matching photos</td></tr>`;
            return;
        }

        images.forEach((img, idx) => {
            const planned = plannedMap.get(img.abs_path);
            const isSelected = selectedImage && selectedImage.abs_path === img.abs_path;
            const isChecked = selectedImageSet.has(img.abs_path);

            const tr = document.createElement('tr');
            if (isSelected) tr.classList.add('selected');

            tr.innerHTML = `
                <td><input type="checkbox" class="row-checkbox" ${isChecked ? 'checked' : ''}></td>
                <td><img class="table-thumb" src="/api/thumbnail?path=${encodeURIComponent(img.abs_path)}" loading="lazy"></td>
                <td><strong title="${img.abs_path}">${img.name}</strong></td>
                <td><span class="badge-${img.orientation[0]}">${img.orientation.toUpperCase()}</span></td>
                <td class="font-mono">${img.width}×${img.height}</td>
                <td><code class="font-mono text-cyan">${planned ? planned.target_filename : '—'}</code></td>
            `;

            tr.addEventListener('click', (e) => {
                if (e.target.classList.contains('row-checkbox')) return;
                selectPhoto(img);
            });

            const chk = tr.querySelector('.row-checkbox');
            chk.addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectedImageSet.add(img.abs_path);
                } else {
                    selectedImageSet.delete(img.abs_path);
                }
            });

            tableBody.appendChild(tr);
        });
    }

    selectAllCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            selectedImageSet = new Set(scannedImages.map(img => img.abs_path));
        } else {
            selectedImageSet.clear();
        }
        renderWorkspace();
    });

    // 8. Photo Selection & Preview Inspector
    function selectPhoto(img) {
        selectedImage = img;
        renderWorkspace();

        metaFilename.textContent = img.name;
        metaResolution.textContent = `${img.width} × ${img.height} (${img.format})`;
        metaOrientationSelect.value = img.orientation;

        const planned = plannedMap.get(img.abs_path);
        metaExportName.textContent = planned ? planned.target_filename : '—';

        loadInspectorPreview();
    }

    metaOrientationSelect.addEventListener('change', (e) => {
        if (selectedImage) {
            selectedImage.orientation = e.target.value;
            updatePlannedNames();
            loadInspectorPreview();
            renderWorkspace();
        }
    });

    function triggerDebouncedPreview() {
        if (previewDebounceTimer) clearTimeout(previewDebounceTimer);
        previewDebounceTimer = setTimeout(() => {
            if (selectedImage) {
                loadInspectorPreview();
            }
        }, 200);
    }

    async function loadInspectorPreview() {
        if (!selectedImage) return;

        try {
            const config = getActiveConfig();
            const res = await fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_path: selectedImage.abs_path,
                    wm_vert_path: config.wm_vert_path,
                    wm_horiz_path: config.wm_horiz_path,
                    orientation_override: selectedImage.orientation,
                    config: config
                })
            });
            const data = await res.json();

            if (data.success) {
                compImgOriginal.src = data.original_b64;
                compImgWatermarked.src = data.watermarked_b64;
                metaWatermark.textContent = data.watermark_applied || "None";

                previewEmptyBox.style.display = 'none';
                sliderComparison.style.display = 'flex';
                resetSliderPosition();
            }
        } catch (err) {
            console.error("Preview render error:", err);
        }
    }

    // 9. Comparison Slider Dragging
    function resetSliderPosition() {
        updateSliderPosition(50);
    }

    function updateSliderPosition(percent) {
        percent = Math.max(0, Math.min(100, percent));
        compOverlayClip.style.width = `${percent}%`;
        sliderHandle.style.left = `${percent}%`;
    }

    sliderHandle.addEventListener('mousedown', () => { isSliderDragging = true; });
    window.addEventListener('mouseup', () => { isSliderDragging = false; });
    window.addEventListener('mousemove', (e) => {
        if (!isSliderDragging) return;
        const rect = compWrapper.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const pct = (offsetX / rect.width) * 100;
        updateSliderPosition(pct);
    });

    // Zoom Controls
    btnZoomIn.addEventListener('click', () => {
        zoomScale = Math.min(2.5, zoomScale + 0.25);
        applyZoom();
    });
    btnZoomOut.addEventListener('click', () => {
        zoomScale = Math.max(0.5, zoomScale - 0.25);
        applyZoom();
    });
    btnZoomFit.addEventListener('click', () => {
        zoomScale = 1.0;
        applyZoom();
    });

    function applyZoom() {
        compWrapper.style.transform = `scale(${zoomScale})`;
        zoomLevelText.textContent = zoomScale === 1.0 ? 'Fit' : `${Math.round(zoomScale * 100)}%`;
    }

    // 10. Bottom Job Execution & Progress
    btnStartBatch.addEventListener('click', async () => {
        const targetImages = scannedImages.filter(img => selectedImageSet.has(img.abs_path));
        if (targetImages.length === 0) {
            showToast("No photos selected for batch", "error");
            return;
        }

        const config = getActiveConfig();
        btnStartBatch.disabled = true;
        btnPauseBatch.style.display = 'inline-flex';
        btnCancelBatch.style.display = 'inline-flex';
        btnOpenCompleted.style.display = 'none';

        jobStatusText.textContent = "Starting engine...";
        jobProgressFill.style.width = '0%';
        jobPercentText.textContent = '0%';
        jobCountText.textContent = `0 / ${targetImages.length}`;

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    images: targetImages,
                    config: config
                })
            });
            const data = await res.json();
            if (!data.success) {
                showToast(data.error || "Could not start batch", "error");
                resetJobButtons();
                return;
            }

            startPollingStatus();
            showToast("Batch processing started", "info");
        } catch (err) {
            showToast("Connection failure", "error");
            resetJobButtons();
        }
    });

    btnPauseBatch.addEventListener('click', async () => {
        const isPaused = btnPauseBatch.textContent === "Resume";
        const endpoint = isPaused ? '/api/job/resume' : '/api/job/pause';
        try {
            const res = await fetch(endpoint, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                btnPauseBatch.textContent = isPaused ? "Pause" : "Resume";
                showToast(isPaused ? "Batch resumed" : "Batch paused", "info");
            }
        } catch (err) {
            console.error("Pause/resume error:", err);
        }
    });

    btnCancelBatch.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/job/cancel', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast("Cancelling batch...", "info");
            }
        } catch (err) {
            console.error("Cancel error:", err);
        }
    });

    function resetJobButtons() {
        btnStartBatch.disabled = false;
        btnPauseBatch.style.display = 'none';
        btnCancelBatch.style.display = 'none';
        btnPauseBatch.textContent = "Pause";
    }

    function startPollingStatus() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/status');
                const status = await res.json();

                jobProgressFill.style.width = `${status.percentage}%`;
                jobPercentText.textContent = `${status.percentage}%`;
                jobCountText.textContent = `${status.current} / ${status.total}`;
                jobStatusText.textContent = status.current_file || status.status;

                // Update log drawer
                if (status.logs && status.logs.length > 0) {
                    logTerminal.innerHTML = status.logs.map(l => `<div>${l}</div>`).join('');
                    logTerminal.scrollTop = logTerminal.scrollHeight;
                }

                if (!status.is_running) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    resetJobButtons();

                    if (status.status === "completed") {
                        jobStatusText.textContent = `Completed ${status.current}/${status.total} files`;
                        btnOpenCompleted.style.display = 'inline-flex';
                        showToast("🎉 Batch watermarking completed successfully!", "success");
                    } else if (status.status === "cancelled") {
                        jobStatusText.textContent = "Batch cancelled by user";
                        showToast("Batch cancelled", "info");
                    } else if (status.status === "failed") {
                        jobStatusText.textContent = `Completed with ${status.failed_files?.length || 1} errors`;
                        showToast("Batch completed with errors", "error");
                    }
                }
            } catch (err) {
                console.error("Status polling error:", err);
            }
        }, 350);
    }

    // 11. Folder Opening Handlers
    async function openDirectory(dirPath) {
        if (!dirPath) {
            showToast("No destination folder specified", "error");
            return;
        }
        try {
            const res = await fetch('/api/open-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: dirPath })
            });
            const data = await res.json();
            if (data.success) {
                showToast("Opening folder in File Explorer", "success");
            } else {
                showToast(data.error || "Could not open folder", "error");
            }
        } catch (err) {
            showToast("Error communicating with server", "error");
        }
    }

    btnOpenOutputTop.addEventListener('click', () => openDirectory(outputDirInput.value.trim()));
    btnOpenCompleted.addEventListener('click', () => openDirectory(outputDirInput.value.trim()));

    // 12. Log Drawer Toggle
    btnToggleLogs.addEventListener('click', () => {
        const isClosed = window.getComputedStyle(logDrawer).display === 'none';
        logDrawer.style.display = isClosed ? 'flex' : 'none';
    });
    btnCloseLog.addEventListener('click', () => {
        logDrawer.style.display = 'none';
    });

    // 13. Toast Notification Helper
    function showToast(msg, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = msg;
        document.getElementById('toastContainer').appendChild(toast);
        setTimeout(() => toast.remove(), 3500);
    }
});
