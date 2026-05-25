/**
 * SSE-based decrypt-and-search handler.
 * Streams results from /search?q=... as entries are decrypted server-side.
 */

let searchSource = null;
let searchTotal = 0;
let searchCount = 0;

function startSearch() {
  const query = document.getElementById('search-input').value.trim();
  if (!query) {
    showAllEntries();
    return;
  }

  cancelSearch();

  // Hide default list, show search results
  document.getElementById('entry-list').classList.add('hidden');
  const resultsContainer = document.getElementById('search-results');
  resultsContainer.classList.remove('hidden');
  resultsContainer.querySelector('#search-results-header').textContent = `Searching for "${query}"...`;

  // Clear previous results (keep header)
  const existingCards = resultsContainer.querySelectorAll('.search-result-card');
  existingCards.forEach(el => el.remove());

  // Show progress
  const progress = document.getElementById('search-progress');
  progress.classList.remove('hidden');
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-text').textContent = 'Decrypting entries...';
  document.getElementById('lock-icon').classList.add('decrypt-animating');

  searchCount = 0;
  searchTotal = 0;

  searchSource = new EventSource(`/journal/search?q=${encodeURIComponent(query)}`);

  searchSource.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);

      if (data.done) {
        finishSearch(data.total, query);
        return;
      }

      if (data.total) {
        searchTotal = data.total;
      }

      if (data.progress !== undefined && searchTotal > 0) {
        const pct = Math.round((data.progress / searchTotal) * 100);
        document.getElementById('progress-bar').style.width = pct + '%';
        document.getElementById('progress-text').textContent =
          `Decrypting ${data.progress} / ${searchTotal} entries`;
      }

      if (data.id) {
        searchCount++;
        appendSearchResult(data, resultsContainer);
      }
    } catch (e) {
      console.error('Search event parse error:', e);
    }
  };

  searchSource.onerror = function() {
    finishSearch(searchCount, query);
  };
}

function appendSearchResult(entry, container) {
  const div = document.createElement('div');
  div.className = 'search-result-card group px-4 py-3 rounded border border-border hover:border-muted bg-panel hover:bg-white/[0.02] transition-all';

  const tagsHtml = (entry.tags || [])
    .map(t => `<span class="text-xs px-1.5 py-0.5 rounded border border-muted text-muted">${escHtml(t)}</span>`)
    .join(' ');

  div.innerHTML = `
    <a href="/journal/${entry.id}" class="block">
      <div class="text-sm font-medium text-primary hover:text-white transition-colors">${escHtml(entry.title)}</div>
      <div class="flex items-center gap-3 mt-1 flex-wrap">
        <span class="text-xs text-muted">${entry.created_at ? entry.created_at.slice(0, 10) : ''}</span>
        ${entry.emotion_label ? `<span class="text-xs text-subtle italic">${escHtml(entry.emotion_label)}</span>` : ''}
        ${tagsHtml}
      </div>
      ${entry.excerpt ? `<p class="text-xs text-muted mt-1 line-clamp-2">${escHtml(entry.excerpt)}</p>` : ''}
    </a>
  `;
  container.appendChild(div);
}

function finishSearch(total, query) {
  if (searchSource) {
    searchSource.close();
    searchSource = null;
  }
  document.getElementById('progress-bar').style.width = '100%';
  document.getElementById('lock-icon').classList.remove('decrypt-animating');
  document.getElementById('lock-icon').textContent = '🔒';

  const header = document.getElementById('search-results-header');
  if (searchCount === 0) {
    header.textContent = `No entries found for "${query}"`;
  } else {
    header.textContent = `${searchCount} result${searchCount !== 1 ? 's' : ''} for "${query}" (searched ${total} entries)`;
  }

  setTimeout(() => {
    document.getElementById('search-progress').classList.add('hidden');
    document.getElementById('lock-icon').textContent = '🔓';
  }, 1500);
}

function cancelSearch() {
  if (searchSource) {
    searchSource.close();
    searchSource = null;
  }
  document.getElementById('search-progress').classList.add('hidden');
}

function showAllEntries() {
  cancelSearch();
  document.getElementById('entry-list').classList.remove('hidden');
  document.getElementById('search-results').classList.add('hidden');
}

// Allow pressing Enter in search box
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('search-input');
  if (input) {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); startSearch(); }
      if (e.key === 'Escape') { input.value = ''; showAllEntries(); }
    });
  }
});

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
