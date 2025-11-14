class DashboardSearch {
    constructor() {
        this.searchInput = document.getElementById('searchInput');
        this.clearSearchBtn = document.getElementById('clearSearch');
        this.searchResults = document.getElementById('searchResults');
        this.resultsCount = document.getElementById('resultsCount');
        this.filterButtons = document.querySelectorAll('.filter-btn');
        this.noResults = document.getElementById('noResults');

        this.currentFilter = 'rooms';
        this.init();
    }

    init() {
        console.log('DashboardSearch initialized');
        
        // Event listeners
        if (this.searchInput) {
            this.searchInput.addEventListener('input', this.handleSearch.bind(this));
        }
        
        if (this.clearSearchBtn) {
            this.clearSearchBtn.addEventListener('click', this.handleClearSearch.bind(this)); // Renamed method
        }

        // Filter buttons
        this.filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                console.log('Filter button clicked:', e.target.dataset.filter);
                this.setFilter(e.target.dataset.filter);
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                if (this.searchInput) this.searchInput.focus();
            }
            if (e.key === 'Escape') {
                this.handleClearSearch();
            }
        });

        // Initial state
        this.updateClearButton();
        this.setFilter('rooms'); // Set initial filter
    }

    handleSearch() {
        const query = this.searchInput.value.trim().toLowerCase();
        this.updateClearButton();

        if (query.length === 0) {
            this.resetSearch();
            return;
        }

        let totalResults = 0;

        // Search based on current filter
        switch (this.currentFilter) {
            case 'rooms':
                totalResults = this.searchRooms(query);
                break;
            case 'readings':
                totalResults = this.searchReadings(query);
                break;
            case 'all':
                totalResults = this.searchRooms(query) + this.searchReadings(query);
                break;
        }

        // Update UI
        this.updateResults(totalResults, query);
    }

    searchRooms(query) {
        const roomCards = document.querySelectorAll('.room-card');
        let visibleCount = 0;

        roomCards.forEach(card => {
            const roomName = card.dataset.roomName || '';
            const location = card.dataset.location || '';
            const devices = card.dataset.devices || '';
            const temp = card.dataset.temp || '';
            const humidity = card.dataset.humidity || '';

            const matches =
                roomName.includes(query) ||
                location.includes(query) ||
                devices.includes(query) ||
                temp.includes(query) ||
                humidity.includes(query);

            card.style.display = matches ? 'block' : 'none';
            if (matches) visibleCount++;
        });

        // Update room count
        const roomCount = document.querySelector('.room-count');
        if (roomCount) {
            const totalRooms = document.querySelectorAll('.room-card').length;
            const displayText = query ? `${visibleCount}/${totalRooms} rooms` : `${totalRooms} room${totalRooms !== 1 ? 's' : ''}`;
            roomCount.textContent = displayText;
        }

        return visibleCount;
    }

    searchReadings(query) {
        const readingRows = document.querySelectorAll('.reading-row');
        let visibleCount = 0;

        readingRows.forEach(row => {
            const deviceName = row.dataset.deviceName || '';
            const deviceUid = row.dataset.deviceUid || '';
            const deviceType = row.dataset.deviceType || '';
            const temp = row.dataset.temp || '';
            const humidity = row.dataset.humidity || '';
            const motion = row.dataset.motion || '';

            const matches =
                deviceName.includes(query) ||
                deviceUid.includes(query) ||
                deviceType.includes(query) ||
                temp.includes(query) ||
                humidity.includes(query) ||
                motion.includes(query);

            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
        });

        // Update readings count
        const readingsCount = document.querySelector('.readings-count');
        if (readingsCount) {
            const totalReadings = document.querySelectorAll('.reading-row').length;
            const displayText = query ? `${visibleCount}/${totalReadings} readings` : `${totalReadings} reading${totalReadings !== 1 ? 's' : ''}`;
            readingsCount.textContent = displayText;
        }

        return visibleCount;
    }

    setFilter(filter) {
        console.log('Setting filter to:', filter);
        this.currentFilter = filter;

        // Update button states
        this.filterButtons.forEach(btn => {
            const isActive = btn.dataset.filter === filter;
            if (isActive) {
                btn.classList.add('active', 'bg-blue-600', 'text-white');
                btn.classList.remove('inactive', 'bg-gray-600', 'text-gray-300');
            } else {
                btn.classList.remove('active', 'bg-blue-600', 'text-white');
                btn.classList.add('inactive', 'bg-gray-600', 'text-gray-300');
            }
        });

        // Show/hide sections based on filter
        this.updateSectionVisibility();

        // Re-run search if there's a query
        if (this.searchInput && this.searchInput.value.trim()) {
            this.handleSearch();
        } else {
            this.resetSearch();
        }
    }

    updateSectionVisibility() {
        const roomsSection = document.getElementById('roomsSection');
        const readingsSection = document.getElementById('readingsSection');

        switch (this.currentFilter) {
            case 'rooms':
                if (roomsSection) roomsSection.style.display = 'block';
                if (readingsSection) readingsSection.style.display = 'none';
                break;
            case 'readings':
                if (roomsSection) roomsSection.style.display = 'none';
                if (readingsSection) readingsSection.style.display = 'block';
                break;
            case 'all':
                if (roomsSection) roomsSection.style.display = 'block';
                if (readingsSection) readingsSection.style.display = 'block';
                break;
        }
    }

    updateResults(totalResults, query) {
        if (this.resultsCount) {
            this.resultsCount.textContent = totalResults;
        }

        if (totalResults === 0 && query.length > 0) {
            if (this.searchResults) this.searchResults.classList.remove('hidden');
            if (this.noResults) this.noResults.classList.remove('hidden');
        } else {
            if (this.searchResults) this.searchResults.classList.add('hidden');
            if (this.noResults) this.noResults.classList.add('hidden');
        }

        // Update section visibility based on filter and results
        this.updateSectionVisibility();
    }

    resetSearch() {
        // Show all rooms
        document.querySelectorAll('.room-card').forEach(card => {
            card.style.display = 'block';
        });

        // Show all readings
        document.querySelectorAll('.reading-row').forEach(row => {
            row.style.display = '';
        });

        // Reset counts
        const roomCount = document.querySelector('.room-count');
        const readingsCount = document.querySelector('.readings-count');

        if (roomCount) {
            const totalRooms = document.querySelectorAll('.room-card').length;
            roomCount.textContent = `${totalRooms} room${totalRooms !== 1 ? 's' : ''}`;
        }

        if (readingsCount) {
            const totalReadings = document.querySelectorAll('.reading-row').length;
            readingsCount.textContent = `${totalReadings} reading${totalReadings !== 1 ? 's' : ''}`;
        }

        // Hide search UI
        if (this.searchResults) this.searchResults.classList.add('hidden');
        if (this.noResults) this.noResults.classList.add('hidden');

        // Update section visibility based on current filter
        this.updateSectionVisibility();
    }

    handleClearSearch() {
        if (this.searchInput) {
            this.searchInput.value = '';
        }
        this.resetSearch();
        this.updateClearButton();
        if (this.searchInput) this.searchInput.focus();
    }

    updateClearButton() {
        if (this.clearSearchBtn && this.searchInput) {
            if (this.searchInput.value.trim()) {
                this.clearSearchBtn.classList.remove('hidden');
            } else {
                this.clearSearchBtn.classList.add('hidden');
            }
        }
    }
}

// Initialize search when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded - initializing search');
    
    // Check if we're on a page with search functionality
    if (document.getElementById('searchInput')) {
        new DashboardSearch();
        
        // Add search hint
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            // Store original placeholder
            const originalPlaceholder = searchInput.placeholder;
            searchInput.placeholder = originalPlaceholder + ' (Ctrl+K to focus)';
        }
    } else {
        console.log('No search input found on this page');
    }
});