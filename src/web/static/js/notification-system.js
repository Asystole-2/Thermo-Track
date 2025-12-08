class NotificationSystem {
    constructor() {
        this.isDropdownOpen = false;
        this.userRole = document.body.dataset.userRole || 'user';
        // Confirmed audio file access in the provided context
        this.soundPath = '/static/audio/notification.mp3';
        this.init();
        this.initialNotificationCount = 0;
    }

    init() {
        this.bindEvents();
        this.loadNotificationCount(true);
        // Poll for new notifications every 3 seconds
        setInterval(() => this.loadNotificationCount(), 3000);
    }

    globalUnlockAudio() {
        if (this.isAudioUnlocked) return;

        try {
            const audio = new Audio(this.soundPath);
            audio.volume = 0;
            audio.play().then(() => {
                this.isAudioUnlocked = true;
                console.log("[Notification] Audio unlocked by user interaction.");

                // Play the notification sound if the initial count was > 0
                if (this.initialNotificationCount > 0) {
                    this.animateBell();
                    this.playSound(0.8); // Play the sound now, at a slightly lower volume
                }

            }).catch(e => {
                this.isAudioUnlocked = true;
                console.warn("[Notification] Audio unlock failed, relying on user interaction event.");
            });
        } catch (e) {
        }
    }

    playSound(volume = 0.5) {
        if (!this.isAudioUnlocked) return;
        try {
            const audio = new Audio(this.soundPath);
            audio.volume = volume;

            // Attempt to play the audio. The .catch() handles the Promise rejection if the browser blocks autoplay.
            audio.play().then(() => {
                console.log("[Notification] Successfully played sound.");
            }).catch(e => {
                console.warn("[Notification] Audio playback prevented by browser:", e);
            });
        } catch (e) {
            console.error("Error creating audio object:", e);
        }
    }
    // --- END REFINED METHOD ---

    bindEvents() {
        const bell = document.getElementById('notification-bell');
        const dropdown = document.getElementById('notification-dropdown');

        if (!bell || !dropdown) {
            console.warn('Notification bell elements not found');
            return;
        }

        // Toggle dropdown
        bell.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!bell.contains(e.target) && !dropdown.contains(e.target)) {
                this.closeDropdown();
            }
        });

        // Prevent dropdown from closing when clicking inside (except for links/buttons)
        dropdown.addEventListener('click', (e) => {
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON') {
                return; // Allow default behavior for links and buttons
            }
            e.stopPropagation();
        });

        // Close on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isDropdownOpen) {
                this.closeDropdown();
            }
        });
    }

    toggleDropdown() {
        const dropdown = document.getElementById('notification-dropdown');
        if (!dropdown) return;

        const isHidden = dropdown.classList.contains('hidden');

        if (isHidden) {
            dropdown.classList.remove('hidden');
            this.isDropdownOpen = true;
            this.loadNotificationDropdown();
        } else {
            this.closeDropdown();
        }
    }

    closeDropdown() {
        const dropdown = document.getElementById('notification-dropdown');
        if (dropdown) {
            dropdown.classList.add('hidden');
            this.isDropdownOpen = false;
        }
    }

    async loadNotificationCount() {
        try {
            let url = '/api/user/notifications/unread-count';

            // For admin/technician, get pending request count instead
            if (this.userRole === 'admin' || this.userRole === 'technician') {
                url = '/api/admin/pending-requests-count';
            }

            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to fetch notification count');

            const data = await response.json();
            this.updateNotificationCount(data.unread_count || data.pending_count || 0);
        } catch (error) {
            console.error('Error loading notification count:', error);
        }
    }

    updateNotificationCount(count, skipSound = false) {
        const countElement = document.getElementById('notification-count');
        if (!countElement) return;

        // Capture previous count before updating the UI
        const previousCount = parseInt(countElement.dataset.previousCount || 0);

        if (count > 0) {
            countElement.textContent = count > 99 ? '99+' : count;
            countElement.classList.remove('hidden');

            // Play sound and animate if count increased and is greater than 0
            if (count > previousCount && !skipSound) {
                this.animateBell();
                this.playSound();
            }
            countElement.dataset.previousCount = count;
        } else {
            countElement.classList.add('hidden');
            // Reset previous count to ensure sound plays when new notifications arrive after an empty state
            countElement.dataset.previousCount = 0;
        }
    }

    animateBell() {
        const bell = document.getElementById('notification-bell');
        if (bell) {
            bell.classList.add('animate-pulse');
            setTimeout(() => {
                bell.classList.remove('animate-pulse');
            }, 2000);
        }
    }

    async loadNotificationDropdown() {
        const listElement = document.getElementById('notification-list');
        if (!listElement) return;

        listElement.innerHTML = '<div class="p-4 text-center text-gray-400">Loading notifications...</div>';

        try {
            let url = '/api/user/notifications?limit=5';

            // For admin/technician, get pending room requests
            if (this.userRole === 'admin' || this.userRole === 'technician') {
                url = '/api/admin/pending-room-requests?limit=5';
            }

            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to fetch notifications');

            const data = await response.json();

            if (this.userRole === 'admin' || this.userRole === 'technician') {
                this.renderAdminNotifications(data);
            } else {
                this.renderUserNotifications(data);
            }
        } catch (error) {
            console.error('Error loading notifications:', error);
            listElement.innerHTML = '<div class="p-4 text-center text-red-400">Failed to load notifications</div>';
        }
    }

    renderUserNotifications(notifications) {
        const listElement = document.getElementById('notification-list');
        if (!listElement) return;

        if (notifications.length === 0) {
            listElement.innerHTML = '<div class="p-4 text-center text-gray-400">No notifications</div>';
            return;
        }

        listElement.innerHTML = notifications.map(notification => `
            <div class="p-3 border-b border-gray-600 ${!notification.is_read ? 'bg-blue-900/20' : 'hover:bg-gray-700/50'} transition-colors duration-200 cursor-pointer"
                 onclick="notificationSystem.handleNotificationClick('${notification.id}', '${notification.request_id || ''}')">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <div class="font-medium text-white text-sm">${this.escapeHtml(notification.title)}</div>
                        <div class="text-gray-400 text-xs mt-1">${this.escapeHtml(notification.message)}</div>
                        ${notification.room_name ? `
                            <div class="text-gray-500 text-xs mt-1">
                                Room: ${this.escapeHtml(notification.room_name)}
                            </div>
                        ` : ''}
                        <div class="text-gray-500 text-xs mt-1">
                            ${new Date(notification.created_at).toLocaleString()}
                        </div>
                    </div>
                    ${!notification.is_read ? `
                        <button onclick="event.stopPropagation(); notificationSystem.markAsRead('${notification.id}', event)"
                                class="ml-2 text-blue-400 hover:text-blue-300 text-xs transition-colors duration-200 px-2 py-1 rounded bg-blue-900/30 hover:bg-blue-800/50"
                                title="Mark as read">
                            ✓
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    renderAdminNotifications(requests) {
        const listElement = document.getElementById('notification-list');
        if (!listElement) return;

        if (requests.length === 0) {
            listElement.innerHTML = '<div class="p-4 text-center text-gray-400">No pending requests</div>';
            return;
        }

        listElement.innerHTML = requests.map(request => `
            <div class="p-3 border-b border-gray-600 hover:bg-gray-700/50 transition-colors duration-200 cursor-pointer"
                 onclick="notificationSystem.handleRequestClick('${request.id}')">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <div class="font-medium text-white text-sm capitalize">
                            ${this.escapeHtml(request.request_type.replace('_', ' '))} Request
                        </div>
                        <div class="text-gray-400 text-xs mt-1">
                            From: ${this.escapeHtml(request.username)} - ${this.escapeHtml(request.room_name)}
                        </div>
                        ${request.request_type === 'temperature_change' && request.target_temperature ? `
                            <div class="text-gray-400 text-xs">
                                Target: ${request.target_temperature}°C
                            </div>
                        ` : ''}
                        ${request.user_notes ? `
                            <div class="text-gray-400 text-xs mt-1 truncate">
                                "${this.escapeHtml(request.user_notes)}"
                            </div>
                        ` : ''}
                        <div class="text-gray-500 text-xs mt-1">
                            ${new Date(request.created_at).toLocaleString()}
                        </div>
                    </div>
                    <span class="ml-2 bg-yellow-500 text-white text-xs px-2 py-1 rounded-full capitalize">
                        ${request.status}
                    </span>
                </div>
            </div>
        `).join('');
    }

    handleNotificationClick(notificationId, requestId) {
        // Mark as read first
        this.markAsRead(notificationId);

        // If it's related to a request, navigate to the request
        if (requestId) {
            window.location.href = `${this.getNotificationsPageUrl()}?request_id=${requestId}&notification_id=${notificationId}`;
        } else {
            // Otherwise just go to the notifications page
            window.location.href = this.getNotificationsPageUrl();
        }

        this.closeDropdown();
    }

    handleRequestClick(requestId) {
        // For admin/technician, navigate to the specific request in admin panel
        window.location.href = `${this.getAdminRequestsPageUrl()}?request_id=${requestId}&focus=true`;
        this.closeDropdown();
    }

    getNotificationsPageUrl() {
        return '/notifications';
    }

    getAdminRequestsPageUrl() {
        return '/admin/room-requests';
    }

    async markAsRead(notificationId, event = null) {
        if (event) {
            event.stopPropagation();
        }

        try {
            const response = await fetch(`/api/user/notifications/${notificationId}/read`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                // Reload both the dropdown and count
                this.loadNotificationDropdown();
                this.loadNotificationCount();
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    async markAllAsRead() {
        try {
            // For regular users, mark all notifications as read
            if (this.userRole === 'user' || this.userRole === 'viewer') {
                const response = await fetch('/api/user/notifications/read-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (response.ok) {
                    this.loadNotificationDropdown();
                    this.loadNotificationCount();
                    this.closeDropdown();
                }
            } else {
                // For admin/technician, just close the dropdown
                this.closeDropdown();
            }
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
        }
    }

    escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// Initialize notification system when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.notificationSystem = new NotificationSystem();
    window.unlockAudio = window.notificationSystem.globalUnlockAudio.bind(window.notificationSystem);});