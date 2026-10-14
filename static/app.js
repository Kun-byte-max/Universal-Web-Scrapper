function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function safeUrl(raw) {
    if (!raw || typeof raw !== 'string') return '';
    const trimmed = raw.trim();
    if (!trimmed) return '';

    // Reject protocol-relative URLs (e.g. //evil.com)
    if (trimmed.startsWith('//')) return '';

    try {
        // Permit absolute http:// and https:// URLs
        if (/^https?:\/\//i.test(trimmed)) {
            const parsed = new URL(trimmed);
            if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                return escapeHtml(trimmed);
            }
            return '';
        }
        // Permit ordinary root-relative paths (starting with / but not //)
        if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
            return escapeHtml(trimmed);
        }
    } catch (_) {
        return '';
    }
    return '';
}

if (typeof document !== 'undefined') {
document.addEventListener('DOMContentLoaded', () => {
    // Form elements
    const form = document.getElementById('scrape-form');
    const startBtn = document.getElementById('start-btn');
    const clearBtn = document.getElementById('clear-btn');
    const copyJsonBtn = document.getElementById('copy-json-btn');
    const crawlModeSelect = document.getElementById('crawl-mode');
    const boundedOptions = document.getElementById('bounded-options');
    const modeHint = document.getElementById('mode-hint');

    // Download controls
    const downloadBtn = document.getElementById('download-btn');
    const downloadBundleBtn = document.getElementById('download-bundle-btn');
    const downloadPagesBtn = document.getElementById('download-pages-btn');
    const downloadReportBtn = document.getElementById('download-report-btn');
    const downloadSitemapBtn = document.getElementById('download-sitemap-btn');
    const downloadInventoryBtn = document.getElementById('download-inventory-btn');
    const exportDropdownBtn = document.getElementById('export-dropdown-btn');
    const exportMenu = document.getElementById('export-menu');

    // Inventory & Coverage elements
    const invStatusFilter = document.getElementById('inv-status-filter');
    const invPrevBtn = document.getElementById('inv-prev-btn');
    const invNextBtn = document.getElementById('inv-next-btn');
    const invPageInfo = document.getElementById('inv-page-info');
    const inventoryBody = document.getElementById('inventory-body');

    const invStatDiscovered = document.getElementById('inv-stat-discovered');
    const invStatAttempted = document.getElementById('inv-stat-attempted');
    const invStatCrawled = document.getElementById('inv-stat-crawled');
    const invStatFailed = document.getElementById('inv-stat-failed');
    const invStatSkipped = document.getElementById('inv-stat-skipped');
    const invStatUnattempted = document.getElementById('inv-stat-unattempted');
    const invStatFetchRate = document.getElementById('inv-stat-fetch-rate');
    const invStatExtractRate = document.getElementById('inv-stat-extract-rate');
    const coverageStopReason = document.getElementById('coverage-stop-reason');
    const coverageWarningsBox = document.getElementById('coverage-warnings-box');
    const coverageWarningsList = document.getElementById('coverage-warnings-list');

    // Progress & Stats elements
    const progressContainer = document.getElementById('progress-container');
    const statusMessage = document.getElementById('status-message');
    const progressPercent = document.getElementById('progress-percent');
    const progressBar = document.getElementById('progress-bar');
    const statPages = document.getElementById('stat-pages');
    const statRecords = document.getElementById('stat-records');
    const statDuration = document.getElementById('stat-duration');
    const errorBox = document.getElementById('error-box');
    const errorMessage = document.getElementById('error-message');

    // Display elements
    const resultsBody = document.getElementById('results-body');
    const jsonPreview = document.getElementById('json-preview');
    const jsonDatasetSelect = document.getElementById('json-dataset-select');
    const jsonSizeLabel = document.getElementById('json-size-label');
    const toggleAllSectionsBtn = document.getElementById('toggle-all-sections-btn');
    const pagesWrapper = document.getElementById('pages-wrapper');
    const pagesCountLabel = document.getElementById('pages-count-label');
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    let currentJobId = null;
    let pollInterval = null;
    let currentRecords = [];
    let currentPages = null;
    let currentInventoryItems = [];
    let currentInventoryPage = 1;
    let currentInventoryTotalPages = 1;
    let currentInventoryStatusFilter = '';
    let currentCoverageSummary = null;

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const targetTab = btn.getAttribute('data-tab');
            const targetEl = document.getElementById(targetTab);
            if (targetEl) targetEl.classList.add('active');

            if (targetTab === 'pages-tab' && currentJobId && currentPages === null) {
                await loadVisitedPages(currentJobId);
            } else if (targetTab === 'inventory-tab' && currentJobId) {
                await loadJobCoverageAndInventory(currentJobId);
            } else if (targetTab === 'json-tab') {
                if (jsonDatasetSelect && jsonDatasetSelect.value === 'pages' && currentJobId && currentPages === null) {
                    await loadVisitedPages(currentJobId);
                } else if (jsonDatasetSelect && jsonDatasetSelect.value === 'inventory' && currentJobId && (!currentInventoryItems || currentInventoryItems.length === 0)) {
                    await loadJobInventory(currentJobId, 1, '');
                }
                updateJsonPreview();
            }
        });
    });

    // Crawl Mode Toggle
    if (crawlModeSelect) {
        crawlModeSelect.addEventListener('change', () => {
            if (crawlModeSelect.value === 'bounded') {
                boundedOptions.style.display = 'flex';
                if (modeHint) modeHint.textContent = 'Limits crawl to specific page and record counts';
                if (!document.getElementById('max-pages').value) document.getElementById('max-pages').value = '5';
                if (!document.getElementById('max-records').value) document.getElementById('max-records').value = '50';
            } else {
                boundedOptions.style.display = 'none';
                if (modeHint) modeHint.textContent = 'Automatically crawls entire website until queue is exhausted';
            }
        });
    }

    // Export Dropdown Toggle
    if (exportDropdownBtn && exportMenu) {
        exportDropdownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportMenu.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!exportMenu.contains(e.target) && e.target !== exportDropdownBtn) {
                exportMenu.classList.add('hidden');
            }
        });
    }

    function setDownloadControlsState(enabled) {
        if (downloadBtn) downloadBtn.disabled = !enabled;
        if (downloadBundleBtn) downloadBundleBtn.disabled = !enabled;
        if (downloadPagesBtn) downloadPagesBtn.disabled = !enabled;
        if (downloadReportBtn) downloadReportBtn.disabled = !enabled;
        if (downloadSitemapBtn) downloadSitemapBtn.disabled = !enabled;
        if (downloadInventoryBtn) downloadInventoryBtn.disabled = !enabled;
        if (exportDropdownBtn) exportDropdownBtn.disabled = !enabled;
        if (!enabled && exportMenu) exportMenu.classList.add('hidden');
    }

    async function triggerDownload(type) {
        if (!currentJobId) {
            showError('No active job selected for download.');
            return;
        }
        let url;
        let defaultFilename;
        if (type === 'bundle') {
            url = `/api/jobs/${encodeURIComponent(currentJobId)}/download/bundle`;
            defaultFilename = `scrape_bundle_${currentJobId}.zip`;
        } else if (type === 'legacy') {
            url = `/api/jobs/${encodeURIComponent(currentJobId)}/download`;
            defaultFilename = `scrape_results_${currentJobId.substring(0, 8)}.json`;
        } else {
            url = `/api/jobs/${encodeURIComponent(currentJobId)}/download/${encodeURIComponent(type)}`;
            defaultFilename = `${type}.json`;
        }

        if (exportMenu) exportMenu.classList.add('hidden');

        try {
            const res = await fetch(url);
            if (!res.ok) {
                let errMsg = `Download failed (HTTP ${res.status})`;
                try {
                    const errData = await res.json();
                    errMsg = formatErrorDetail(errData.detail || errData.message || errMsg);
                } catch (_) {}
                showError(errMsg);
                return;
            }

            const blob = await res.blob();
            const blobUrl = URL.createObjectURL(blob);

            let filename = defaultFilename;
            const disposition = res.headers.get('content-disposition');
            if (disposition) {
                const match = disposition.match(/filename="?([^";]+)"?/);
                if (match && match[1]) {
                    filename = match[1].trim();
                }
            }

            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = filename;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
        } catch (err) {
            showError(`Download request failed: ${err.message}`);
        }
    }

    // Download event listeners
    if (downloadBtn) downloadBtn.addEventListener('click', () => triggerDownload('products'));
    if (downloadBundleBtn) downloadBundleBtn.addEventListener('click', () => triggerDownload('bundle'));
    if (downloadPagesBtn) downloadPagesBtn.addEventListener('click', () => triggerDownload('pages'));
    if (downloadReportBtn) downloadReportBtn.addEventListener('click', () => triggerDownload('report'));
    if (downloadSitemapBtn) downloadSitemapBtn.addEventListener('click', () => triggerDownload('sitemap'));
    if (downloadInventoryBtn) downloadInventoryBtn.addEventListener('click', () => triggerDownload('inventory'));

    function formatErrorDetail(detail) {
        if (!detail) return 'Failed to initialize scrape job';
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) {
            return detail.map(err => {
                if (typeof err === 'string') return err;
                const field = Array.isArray(err.loc) ? err.loc.filter(l => l !== 'body').join('.') : '';
                const prefix = field ? `[${field}] ` : '';
                return `${prefix}${err.msg || JSON.stringify(err)}`;
            }).join('; ');
        }
        if (typeof detail === 'object') {
            return detail.msg || detail.message || JSON.stringify(detail);
        }
        return String(detail);
    }

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = document.getElementById('url').value.trim();
        const mode = crawlModeSelect ? crawlModeSelect.value : 'auto';
        const useBrowser = document.getElementById('use-browser').checked;

        if (!url) return;

        const payload = {
            url: url,
            mode: mode,
            use_browser_fallback: useBrowser
        };

        if (mode === 'bounded') {
            const maxPagesVal = document.getElementById('max-pages').value.trim();
            const maxRecordsVal = document.getElementById('max-records').value.trim();
            const maxPages = parseInt(maxPagesVal, 10);
            const maxRecords = parseInt(maxRecordsVal, 10);

            if (isNaN(maxPages) || maxPages < 1) {
                showError('Please enter a valid Max Pages number (minimum 1) for bounded mode.');
                return;
            }
            if (isNaN(maxRecords) || maxRecords < 1) {
                showError('Please enter a valid Max Records number (minimum 1) for bounded mode.');
                return;
            }
            payload.max_pages = maxPages;
            payload.max_records = maxRecords;
        }

        // Reset UI
        clearResults();
        setLoading(true);
        errorBox.classList.add('hidden');

        try {
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(formatErrorDetail(errData.detail || errData.message));
            }

            const data = await response.json();
            currentJobId = data.job_id;
            
            // Start Polling Job Status
            pollInterval = setInterval(() => pollJobStatus(currentJobId), 1000);

        } catch (err) {
            showError(err.message);
            setLoading(false);
        }
    });

    // Poll Job Status
    async function pollJobStatus(jobId) {
        try {
            const res = await fetch(`/api/jobs/${jobId}`);
            if (!res.ok) throw new Error('Failed to fetch job status');

            const job = await res.json();
            
            // Update UI Stats & Progress
            statusMessage.textContent = job.status_message || job.status;
            progressPercent.textContent = `${job.progress || 0}%`;
            progressBar.style.width = `${job.progress || 0}%`;

            if (job.stats) {
                statPages.textContent = job.stats.pages_visited || 0;
                statRecords.textContent = job.stats.records_extracted || 0;
                statDuration.textContent = `${job.stats.duration_seconds || 0}s`;
            }

            if (job.status === 'completed') {
                clearInterval(pollInterval);
                setLoading(false);
                currentRecords = job.records || [];
                renderResults(currentRecords);
                setDownloadControlsState(true);

                // Pre-load visited pages and inventory
                loadVisitedPages(jobId);
                loadJobCoverageAndInventory(jobId);

                if (currentRecords.length === 0) {
                    showError("Scrape finished, but zero structured records could be extracted from this site.");
                }

            } else if (job.status === 'failed') {
                clearInterval(pollInterval);
                setLoading(false);
                currentRecords = job.records || [];
                if (currentRecords.length > 0) {
                    renderResults(currentRecords);
                    setDownloadControlsState(true);
                    loadVisitedPages(jobId);
                }
                loadJobCoverageAndInventory(jobId);
                showError(job.error || 'Scrape job failed');
            }

        } catch (err) {
            clearInterval(pollInterval);
            setLoading(false);
            showError(err.message);
        }
    }

    // Load visited pages from /api/jobs/{job_id}/pages
    async function loadVisitedPages(jobId) {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/pages`);
            if (!res.ok) return;
            const pages = await res.json();
            currentPages = Array.isArray(pages) ? pages : [];
            renderPages(currentPages);
            if (jsonDatasetSelect && jsonDatasetSelect.value === 'pages') {
                updateJsonPreview();
            }
        } catch (e) {
            console.error('Error fetching visited pages:', e);
        }
    }

    // Render individual section blocks (paragraphs, lists, tables, images, links)
    function renderSectionBlocks(blocks) {
        if (!blocks || !Array.isArray(blocks) || blocks.length === 0) return '';
        return blocks.map(b => {
            const bType = b.type;
            if (bType === 'paragraph') {
                return `<div class="section-block block-paragraph"><p>${escapeHtml(b.text)}</p></div>`;
            } else if (bType === 'list') {
                const tag = b.ordered ? 'ol' : 'ul';
                const itemsHtml = (b.items || []).map(it => `<li>${escapeHtml(it)}</li>`).join('');
                return `<div class="section-block block-list"><${tag} class="content-list">${itemsHtml}</${tag}></div>`;
            } else if (bType === 'table') {
                const headers = b.headers || [];
                const rows = b.rows || [];
                const thHtml = headers.map(h => `<th>${escapeHtml(h)}</th>`).join('');
                const trHtml = rows.map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('');
                return `
                    <div class="section-block block-table table-wrapper">
                        <table class="content-table">
                            ${headers.length > 0 ? `<thead><tr>${thHtml}</tr></thead>` : ''}
                            <tbody>${trHtml}</tbody>
                        </table>
                    </div>
                `;
            } else if (bType === 'image') {
                const safeSrc = safeUrl(b.image_url);
                const caption = b.caption ? `<div class="block-img-meta"><span class="meta-label">Caption:</span> ${escapeHtml(b.caption)}</div>` : '';
                const alt = b.alt ? `<div class="block-img-meta"><span class="meta-label">Alt:</span> ${escapeHtml(b.alt)}</div>` : '';
                const title = b.title ? `<div class="block-img-meta"><span class="meta-label">Title:</span> ${escapeHtml(b.title)}</div>` : '';
                return `
                    <div class="section-block block-image-card">
                        <img src="${safeSrc || 'https://via.placeholder.com/64?text=Img'}" class="block-img-thumb" alt="${escapeHtml(b.alt || 'Content Image')}" onerror="this.onerror=null;this.src='https://via.placeholder.com/64?text=Img';">
                        <div class="block-img-info">
                            ${caption}
                            ${alt}
                            ${title}
                            ${safeSrc ? `<a href="${safeSrc}" target="_blank" rel="noopener" class="meta-link">View Original ↗</a>` : ''}
                        </div>
                    </div>
                `;
            } else if (bType === 'link') {
                const safeHref = safeUrl(b.url);
                const badge = b.is_asset ? `<span class="badge-asset">📥 Downloadable Asset</span>` : `<span class="badge-link">🔗 Link</span>`;
                return `
                    <div class="section-block block-link-item">
                        ${badge}
                        ${safeHref ? `<a href="${safeHref}" target="_blank" rel="noopener" class="content-link">${escapeHtml(b.text || b.url)} ↗</a>` : escapeHtml(b.text || b.url)}
                    </div>
                `;
            } else if (bType === 'quote') {
                return `<div class="section-block block-quote"><blockquote>${escapeHtml(b.text)}</blockquote></div>`;
            } else if (bType === 'code') {
                return `<div class="section-block block-code"><pre><code>${escapeHtml(b.text)}</code></pre></div>`;
            }
            return '';
        }).join('');
    }

    // Render hierarchical section tree recursively
    function renderSectionTree(sections, depth = 0) {
        if (!sections || !Array.isArray(sections) || sections.length === 0) return '';
        return sections.map(sec => {
            const h = sec.heading || (depth === 0 ? 'Preamble / Introduction' : 'Untitled Section');
            const lvl = sec.level ? `H${sec.level}` : 'ROOT';
            const subtitle = sec.subtitle ? `<div class="section-subtitle"><strong>Subtitle:</strong> ${escapeHtml(sec.subtitle)}</div>` : '';
            const blocksHtml = renderSectionBlocks(sec.blocks);
            const subsecsHtml = sec.subsections && sec.subsections.length > 0
                ? `<div class="subsections-list">${renderSectionTree(sec.subsections, depth + 1)}</div>`
                : '';

            const blockCount = (sec.blocks || []).length;
            const subsecCount = (sec.subsections || []).length;

            return `
                <div class="section-card depth-${depth}">
                    <div class="section-header">
                        <div class="section-title-row">
                            <span class="section-level-badge">${lvl}</span>
                            <strong class="section-heading-text">${escapeHtml(h)}</strong>
                        </div>
                        <div class="section-counts-badge">
                            ${blockCount} block${blockCount !== 1 ? 's' : ''}${subsecCount > 0 ? `, ${subsecCount} sub-sec` : ''}
                        </div>
                    </div>
                    ${subtitle}
                    ${blocksHtml ? `<div class="section-blocks">${blocksHtml}</div>` : ''}
                    ${subsecsHtml}
                </div>
            `;
        }).join('');
    }

    // Render Visited Pages Preview (Full Structured Content without truncation)
    function renderPages(pages) {
        if (!pagesWrapper) return;
        if (pagesCountLabel) pagesCountLabel.textContent = `Visited Pages Inventory (${pages.length})`;

        if (!pages || pages.length === 0) {
            pagesWrapper.innerHTML = `
                <div class="empty-state">
                    No visited pages recorded for this job.
                </div>
            `;
            return;
        }

        pagesWrapper.innerHTML = pages.map((pg, idx) => {
            const title = escapeHtml(pg.title || 'Untitled Page');
            const pageUrlRaw = pg.page_url || pg.url || '';
            const safePageUrl = safeUrl(pageUrlRaw);
            const pageType = escapeHtml(pg.page_type || 'page');
            const status = pg.http_status || 200;

            const pageContent = pg.page_content || {};
            const contentExt = pg.content_extraction || {};
            const sections = pageContent.sections || [];
            const fullText = pageContent.full_text || pg.main_text || '';
            const paragraphs = pg.paragraphs || [];
            const lists = pg.lists || [];
            const tables = pg.tables || [];
            const images = pg.images || [];
            const downloadables = pg.downloadable_files || [];

            // Completeness status
            const isComplete = contentExt.complete ?? true;
            const extStatus = contentExt.status || 'complete';
            const completePill = isComplete
                ? `<span class="badge-complete">✓ Complete</span>`
                : `<span class="badge-incomplete">⚠️ ${escapeHtml(extStatus)}</span>`;

            // Warnings
            const warnings = contentExt.warnings || [];
            const warningsHtml = warnings.length > 0
                ? `<div class="page-warnings-alert"><ul>${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul></div>`
                : '';

            // Downloadable files
            let downloadsHtml = '';
            if (downloadables.length > 0) {
                const filesList = downloadables.map(df => {
                    const safeHref = safeUrl(df.url);
                    const ext = escapeHtml((df.file_type || 'file').toUpperCase());
                    const name = escapeHtml(df.anchor_text || df.url);
                    return `
                        <div class="download-item-card">
                            <span class="file-ext-badge">${ext}</span>
                            <div class="file-info">
                                ${safeHref ? `<a href="${safeHref}" target="_blank" rel="noopener" class="file-name">${name} ↗</a>` : `<span class="file-name">${name}</span>`}
                                <div class="file-url">${escapeHtml(df.url)}</div>
                            </div>
                        </div>
                    `;
                }).join('');
                downloadsHtml = `
                    <div class="page-downloads-section">
                        <div class="section-group-title">📥 Downloadable Files & Assets (${downloadables.length})</div>
                        <div class="downloads-grid">${filesList}</div>
                    </div>
                `;
            }

            // Headings Summary
            let headingsSummary = '';
            if (pg.headings && typeof pg.headings === 'object') {
                const parts = [];
                for (const [tag, list] of Object.entries(pg.headings)) {
                    if (Array.isArray(list) && list.length > 0) {
                        const items = list.slice(0, 3).map(h => escapeHtml(h)).join('; ');
                        const more = list.length > 3 ? ` (+${list.length - 3} more)` : '';
                        parts.push(`<div><strong>${escapeHtml(tag.toUpperCase())}:</strong> ${items}${more}</div>`);
                    }
                }
                if (parts.length > 0) {
                    headingsSummary = `<div class="page-headings-block">${parts.join('')}</div>`;
                }
            }

            const urlMarkup = safePageUrl
                ? `<a href="${safePageUrl}" target="_blank" rel="noopener" class="page-card-url">${escapeHtml(pageUrlRaw)} ↗</a>`
                : (pageUrlRaw ? `<span class="page-card-url">${escapeHtml(pageUrlRaw)}</span>` : '');

            return `
                <div class="page-card">
                    <div class="page-card-top">
                        <div class="page-card-title">${idx + 1}. ${title}</div>
                        <div class="page-badges">
                            ${completePill}
                            <span class="badge-type">${pageType}</span>
                            <span class="badge-status">HTTP ${status}</span>
                        </div>
                    </div>
                    ${urlMarkup}
                    ${warningsHtml}

                    <div class="page-metrics-strip">
                        <div class="metric-chip"><strong>${sections.length}</strong> Sections</div>
                        <div class="metric-chip"><strong>${paragraphs.length}</strong> Paragraphs</div>
                        <div class="metric-chip"><strong>${lists.length}</strong> Lists</div>
                        <div class="metric-chip"><strong>${tables.length}</strong> Tables</div>
                        <div class="metric-chip"><strong>${images.length}</strong> Images</div>
                        <div class="metric-chip"><strong>${downloadables.length}</strong> Files</div>
                        <div class="metric-chip"><strong>${fullText.length.toLocaleString()}</strong> Chars</div>
                    </div>

                    ${headingsSummary}

                    <div class="page-sections-tree-container">
                        <div class="section-group-title">Structured Section Hierarchy (Reading Order)</div>
                        ${sections.length > 0 ? renderSectionTree(sections) : `<div class="empty-sections-note">No structured sections extracted.</div>`}
                    </div>

                    ${downloadsHtml}

                    ${fullText ? `
                        <details class="page-fulltext-accordion">
                            <summary>📄 Complete Reconstructed Full Text (${fullText.length.toLocaleString()} characters)</summary>
                            <div class="fulltext-box">${escapeHtml(fullText)}</div>
                        </details>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    // Render Rich Images Cards for a single product record
    function renderRichImagesGallery(images) {
        if (!images || !Array.isArray(images) || images.length === 0) return '';
        return images.map(img => {
            const rawSrc = img.image_url || '';
            const safeSrc = safeUrl(rawSrc);
            const title = img.title ? `<div class="meta-item"><span class="meta-label">Title:</span> <span class="meta-val">${escapeHtml(img.title)}</span></div>` : '';
            const section = img.section_title ? `<div class="meta-item"><span class="meta-label">Section:</span> <span class="meta-val">${escapeHtml(img.section_title)}</span></div>` : '';
            const alt = img.alt ? `<div class="meta-item"><span class="meta-label">Alt:</span> <span class="meta-val">${escapeHtml(img.alt)}</span></div>` : '';
            const caption = img.caption ? `<div class="meta-item"><span class="meta-label">Caption:</span> <span class="meta-val">${escapeHtml(img.caption)}</span></div>` : '';
            return `
                <div class="rich-image-card">
                    <img src="${safeSrc || 'https://via.placeholder.com/64?text=Img'}" class="rich-image-thumb" alt="${escapeHtml(img.alt || 'Product Image')}" onerror="this.onerror=null;this.src='https://via.placeholder.com/64?text=Img';">
                    <div class="rich-image-meta">
                        ${title}
                        ${section}
                        ${alt}
                        ${caption}
                        ${safeSrc ? `<a href="${safeSrc}" target="_blank" rel="noopener" class="meta-link">View Original ↗</a>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    // Render Table & JSON Preview
    function renderResults(records) {
        if (!records || records.length === 0) {
            resultsBody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">No records found.</td>
                </tr>
            `;
            jsonPreview.textContent = '[ ]';
            return;
        }

        // Render Table Rows (with expandable rich images subrows)
        resultsBody.innerHTML = records.map((rec, idx) => {
            const hasImages = Array.isArray(rec.images) && rec.images.length > 0;
            const imagesBadge = hasImages
                ? `<br><button type="button" class="badge-images-toggle" data-idx="${idx}">🖼️ ${rec.images.length} Structured Images ▼</button>`
                : '';

            const subRow = hasImages
                ? `<tr id="images-subrow-${idx}" class="images-detail-row hidden">
                     <td colspan="6">
                         <div class="rich-images-gallery">
                             ${renderRichImagesGallery(rec.images)}
                         </div>
                     </td>
                   </tr>`
                : '';

            const safeMainImg = safeUrl(rec.image_url);
            const rawLink = rec.product_url || rec.source_url || '';
            const safeProductLink = safeUrl(rawLink);

            return `
                <tr>
                    <td>${idx + 1}</td>
                    <td>
                        ${safeMainImg ? `<img src="${safeMainImg}" class="thumb-img" alt="preview" onerror="this.onerror=null;this.src='https://via.placeholder.com/48?text=No+Img'">` : 'N/A'}
                    </td>
                    <td>
                        <strong>${escapeHtml(rec.title || 'Untitled')}</strong>
                        ${rec.description ? `<br><small>${escapeHtml(rec.description.substring(0, 110))}...</small>` : ''}
                        ${imagesBadge}
                    </td>
                    <td>${rec.price ? `${escapeHtml(rec.currency || '')} ${escapeHtml(String(rec.price))}` : 'N/A'}</td>
                    <td>
                        ${rec.brand ? `<div>Brand: ${escapeHtml(rec.brand)}</div>` : ''}
                        ${rec.sku ? `<div>SKU: ${escapeHtml(rec.sku)}</div>` : 'N/A'}
                    </td>
                    <td>
                        ${safeProductLink ? `<a href="${safeProductLink}" target="_blank" rel="noopener">Link ↗</a>` : 'N/A'}
                    </td>
                </tr>
                ${subRow}
            `;
        }).join('');

        // Render JSON Code Block
        updateJsonPreview();
    }

    // Function to update the formatted JSON preview based on selected dataset
    function updateJsonPreview() {
        if (!jsonPreview) return;
        const mode = jsonDatasetSelect ? jsonDatasetSelect.value : 'products';
        let dataToDisplay = [];
        let countText = '0 items';
        if (mode === 'products') {
            dataToDisplay = currentRecords || [];
            countText = `${dataToDisplay.length} records`;
        } else if (mode === 'pages') {
            dataToDisplay = currentPages || [];
            countText = `${dataToDisplay.length} pages`;
        } else if (mode === 'inventory') {
            dataToDisplay = currentInventoryItems || [];
            countText = `${dataToDisplay.length} URLs`;
        }
        if (jsonSizeLabel) jsonSizeLabel.textContent = countText;
        jsonPreview.textContent = JSON.stringify(dataToDisplay, null, 2);
    }

    if (jsonDatasetSelect) {
        jsonDatasetSelect.addEventListener('change', async () => {
            if (jsonDatasetSelect.value === 'pages' && currentJobId && currentPages === null) {
                await loadVisitedPages(currentJobId);
            } else if (jsonDatasetSelect.value === 'inventory' && currentJobId && (!currentInventoryItems || currentInventoryItems.length === 0)) {
                await loadJobInventory(currentJobId, 1, '');
            }
            updateJsonPreview();
        });
    }

    if (toggleAllSectionsBtn) {
        let allExpanded = false;
        toggleAllSectionsBtn.addEventListener('click', () => {
            allExpanded = !allExpanded;
            const accordions = document.querySelectorAll('.page-fulltext-accordion');
            accordions.forEach(acc => acc.open = allExpanded);
            toggleAllSectionsBtn.textContent = allExpanded
                ? '📑 Collapse All Details'
                : '📑 Expand All Details';
        });
    }

    // Delegate clicks for images toggle buttons
    if (resultsBody) {
        resultsBody.addEventListener('click', (e) => {
            const toggleBtn = e.target.closest('.badge-images-toggle');
            if (toggleBtn) {
                const idx = toggleBtn.getAttribute('data-idx');
                const subRow = document.getElementById(`images-subrow-${idx}`);
                if (subRow) {
                    const isHidden = subRow.classList.contains('hidden');
                    subRow.classList.toggle('hidden');
                    toggleBtn.textContent = isHidden
                        ? toggleBtn.textContent.replace('▼', '▲')
                        : toggleBtn.textContent.replace('▲', '▼');
                }
            }
        });
    }

    // Copy JSON Button Handler
    copyJsonBtn.addEventListener('click', () => {
        const mode = jsonDatasetSelect ? jsonDatasetSelect.value : 'products';
        let dataToCopy = [];
        if (mode === 'products') dataToCopy = currentRecords || [];
        else if (mode === 'pages') dataToCopy = currentPages || [];
        else if (mode === 'inventory') dataToCopy = currentInventoryItems || [];

        if (!dataToCopy || dataToCopy.length === 0) return;
        navigator.clipboard.writeText(JSON.stringify(dataToCopy, null, 2));
        const originalText = copyJsonBtn.textContent;
        copyJsonBtn.textContent = 'Copied! ✓';
        setTimeout(() => copyJsonBtn.textContent = originalText, 2000);
    });

    // Inventory Toolbar Listeners
    if (invStatusFilter) {
        invStatusFilter.addEventListener('change', () => {
            currentInventoryPage = 1;
            currentInventoryStatusFilter = invStatusFilter.value;
            if (currentJobId) {
                loadJobInventory(currentJobId, currentInventoryPage, currentInventoryStatusFilter);
            }
        });
    }

    if (invPrevBtn) {
        invPrevBtn.addEventListener('click', () => {
            if (currentInventoryPage > 1 && currentJobId) {
                currentInventoryPage--;
                loadJobInventory(currentJobId, currentInventoryPage, currentInventoryStatusFilter);
            }
        });
    }

    if (invNextBtn) {
        invNextBtn.addEventListener('click', () => {
            if (currentInventoryPage < currentInventoryTotalPages && currentJobId) {
                currentInventoryPage++;
                loadJobInventory(currentJobId, currentInventoryPage, currentInventoryStatusFilter);
            }
        });
    }

    async function loadJobCoverageAndInventory(jobId) {
        if (!jobId) return;
        try {
            const repRes = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/download/report`);
            if (repRes.ok) {
                const report = await repRes.json();
                renderCoverageSummary(report.coverage_summary, report.stop_reason);
            }
        } catch (e) {
            console.error('Error fetching coverage report:', e);
        }
        await loadJobInventory(jobId, currentInventoryPage, currentInventoryStatusFilter);
    }

    function renderCoverageSummary(coverage, stopReason) {
        if (!coverage) return;
        currentCoverageSummary = coverage;
        if (invStatDiscovered) invStatDiscovered.textContent = coverage.total_urls_discovered ?? 0;
        if (invStatAttempted) invStatAttempted.textContent = coverage.urls_attempted ?? 0;
        if (invStatCrawled) invStatCrawled.textContent = coverage.pages_crawled_successfully ?? 0;
        if (invStatFailed) invStatFailed.textContent = coverage.urls_failed ?? 0;
        if (invStatSkipped) invStatSkipped.textContent = coverage.urls_skipped ?? 0;
        if (invStatUnattempted) invStatUnattempted.textContent = coverage.urls_pending_or_unattempted ?? 0;
        if (invStatFetchRate) invStatFetchRate.textContent = `${Math.round((coverage.fetch_success_rate || 0) * 100)}%`;
        if (invStatExtractRate) invStatExtractRate.textContent = `${Math.round((coverage.content_extraction_rate || 0) * 100)}%`;

        if (coverageStopReason) {
            const reason = coverage.crawl_stop_reason || stopReason || 'ready';
            coverageStopReason.textContent = `Stop Reason: ${reason.replace(/_/g, ' ')}`;
        }

        const warnings = [...(coverage.warnings || []), ...(coverage.discrepancies || [])];
        if (coverageWarningsBox && coverageWarningsList) {
            if (warnings.length > 0) {
                coverageWarningsList.innerHTML = warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('');
                coverageWarningsBox.classList.remove('hidden');
            } else {
                coverageWarningsBox.classList.add('hidden');
            }
        }
    }

    async function loadJobInventory(jobId, page, status) {
        if (!jobId || !inventoryBody) return;
        inventoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">Loading inventory records...</td></tr>`;

        try {
            let url = `/api/jobs/${encodeURIComponent(jobId)}/inventory?page=${page}&page_size=50`;
            if (status) {
                url += `&status=${encodeURIComponent(status)}`;
            }
            const res = await fetch(url);
            if (!res.ok) {
                inventoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">Unable to load inventory (HTTP ${res.status}).</td></tr>`;
                return;
            }
            const data = await res.json();
            currentInventoryPage = data.page;
            currentInventoryTotalPages = data.total_pages || 1;
            currentInventoryItems = data.items || [];
            if (jsonDatasetSelect && jsonDatasetSelect.value === 'inventory') {
                updateJsonPreview();
            }

            if (invPageInfo) invPageInfo.textContent = `Page ${data.page} of ${currentInventoryTotalPages} (${data.total_items} items)`;
            if (invPrevBtn) invPrevBtn.disabled = (data.page <= 1);
            if (invNextBtn) invNextBtn.disabled = (data.page >= currentInventoryTotalPages);

            renderInventoryTable(data.items || [], (data.page - 1) * data.page_size);
        } catch (err) {
            inventoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">Error loading inventory: ${escapeHtml(err.message)}</td></tr>`;
        }
    }

    function renderInventoryTable(items, offset) {
        if (!inventoryBody) return;
        if (!items || items.length === 0) {
            inventoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">No inventory items matched the current filter.</td></tr>`;
            return;
        }

        inventoryBody.innerHTML = items.map((item, idx) => {
            const num = offset + idx + 1;
            const urlRaw = item.url || '';
            const safeHref = safeUrl(urlRaw);
            const status = escapeHtml(item.status || 'unknown');
            const reason = escapeHtml(item.reason || '-');
            const httpStatus = item.http_status ? escapeHtml(item.http_status) : '-';
            const method = escapeHtml(item.discovery_method || '-');
            const outcome = escapeHtml(item.extraction_outcome || 'not_attempted');

            const urlContent = safeHref
                ? `<a href="${safeHref}" target="_blank" rel="noopener" title="${escapeHtml(urlRaw)}">${escapeHtml(urlRaw)}</a>`
                : escapeHtml(urlRaw);

            return `
                <tr>
                    <td>${num}</td>
                    <td class="inv-url-cell">${urlContent}</td>
                    <td><span class="status-pill ${status}">${status}</span></td>
                    <td><code>${reason}</code></td>
                    <td>${httpStatus}</td>
                    <td>${method}</td>
                    <td><span class="outcome-pill ${outcome}">${outcome}</span></td>
                </tr>
            `;
        }).join('');
    }

    // Clear Results
    clearBtn.addEventListener('click', clearResults);

    function clearResults() {
        if (pollInterval) clearInterval(pollInterval);
        currentJobId = null;
        currentRecords = [];
        currentPages = null;
        currentInventoryPage = 1;
        currentInventoryTotalPages = 1;
        currentInventoryStatusFilter = '';
        currentCoverageSummary = null;
        statPages.textContent = '0';
        statRecords.textContent = '0';
        statDuration.textContent = '0s';
        statusMessage.textContent = 'Ready';
        progressPercent.textContent = '0%';
        progressBar.style.width = '0%';
        progressContainer.classList.add('hidden');
        errorBox.classList.add('hidden');
        resultsBody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">No data extracted yet. Enter a URL and click "Start Scraping".</td>
            </tr>
        `;
        if (pagesWrapper) {
            pagesWrapper.innerHTML = `
                <div class="empty-state">No visited pages data yet. Crawl pages will appear here upon completion.</div>
            `;
        }
        if (pagesCountLabel) pagesCountLabel.textContent = 'Visited Pages Inventory (0)';
        if (inventoryBody) {
            inventoryBody.innerHTML = `<tr><td colspan="7" class="empty-state">No inventory records yet. Run a crawl job to view URL diagnostics.</td></tr>`;
        }
        if (invStatDiscovered) invStatDiscovered.textContent = '0';
        if (invStatAttempted) invStatAttempted.textContent = '0';
        if (invStatCrawled) invStatCrawled.textContent = '0';
        if (invStatFailed) invStatFailed.textContent = '0';
        if (invStatSkipped) invStatSkipped.textContent = '0';
        if (invStatUnattempted) invStatUnattempted.textContent = '0';
        if (invStatFetchRate) invStatFetchRate.textContent = '0%';
        if (invStatExtractRate) invStatExtractRate.textContent = '0%';
        if (coverageStopReason) coverageStopReason.textContent = 'Stop Reason: Ready';
        if (coverageWarningsBox) coverageWarningsBox.classList.add('hidden');
        if (invPageInfo) invPageInfo.textContent = 'Page 1 of 1';
        if (invPrevBtn) invPrevBtn.disabled = true;
        if (invNextBtn) invNextBtn.disabled = true;
        currentInventoryItems = [];
        if (jsonDatasetSelect) jsonDatasetSelect.value = 'products';
        if (jsonSizeLabel) jsonSizeLabel.textContent = '0 items';
        jsonPreview.textContent = '[ ]';
        setDownloadControlsState(false);
        setLoading(false);
    }

    function setLoading(isLoading) {
        startBtn.disabled = isLoading;
        if (isLoading) {
            startBtn.innerHTML = `<span class="btn-icon">⏳</span> Scraping...`;
            progressContainer.classList.remove('hidden');
        } else {
            startBtn.innerHTML = `<span class="btn-icon">⚡</span> Start Scraping`;
        }
    }

    function showError(msg) {
        errorBox.classList.remove('hidden');
        errorMessage.textContent = (typeof msg === 'string') ? msg : formatErrorDetail(msg);
    }
});
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { safeUrl, escapeHtml };
}
