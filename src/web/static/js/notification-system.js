class NotificationSystem {
    constructor() {
        this.isDropdownOpen = false;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadNotificationCount();
        // Poll for new notifications every 30 seconds
        setInterval(() => this.loadNotificationCount(), 30000);
    }

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

        // Prevent dropdown from closing when clicking inside
        dropdown.addEventListener('click', (e) => {
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
            const response = await fetch('/api/user/notifications/unread-count');
            if (!response.ok) throw new Error('Failed to fetch notification count');

            const data = await response.json();
            this.updateNotificationCount(data.unread_count);
        } catch (error) {
            console.error('Error loading notification count:', error);
        }
    }

    updateNotificationCount(count) {
        const countElement = document.getElementById('notification-count');
        if (!countElement) return;

        if (count > 0) {
            countElement.textContent = count > 99 ? '99+' : count;
            countElement.classList.remove('hidden');

            // Add animation for new notifications
            if (count > parseInt(countElement.dataset.previousCount || 0)) {
                this.animateBell();
            }
            countElement.dataset.previousCount = count;
        } else {
            countElement.classList.add('hidden');
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
            const response = await fetch('/api/user/notifications?limit=5');
            if (!response.ok) throw new Error('Failed to fetch notifications');

            const notifications = await response.json();
            this.renderNotifications(notifications);
        } catch (error) {
            console.error('Error loading notifications:', error);
            listElement.innerHTML = '<div class="p-4 text-center text-red-400">Failed to load notifications</div>';
        }
    }

    renderNotifications(notifications) {
        const listElement = document.getElementById('notification-list');
        if (!listElement) return;

        if (notifications.length === 0) {
            listElement.innerHTML = '<div class="p-4 text-center text-gray-400">No notifications</div>';
            return;
        }

        listElement.innerHTML = notifications.map(notification => `
            <div class="p-3 border-b border-gray-600 ${!notification.is_read ? 'bg-blue-900/20' : 'hover:bg-gray-700/50'} transition-colors duration-200">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <div class="font-medium text-white text-sm">${this.escapeHtml(notification.title)}</div>
                        <div class="text-gray-400 text-xs mt-1">${this.escapeHtml(notification.message)}</div>
                        <div class="text-gray-500 text-xs mt-1">
                            ${new Date(notification.created_at).toLocaleString()}
                        </div>
                    </div>
                    ${!notification.is_read ? `
                        <button onclick="event.stopPropagation(); notificationSystem.markAsRead('${notification.id}')"
                                class="ml-2 text-blue-400 hover:text-blue-300 text-xs transition-colors duration-200 px-2 py-1 rounded bg-blue-900/30 hover:bg-blue-800/50"
                                title="Mark as read">
                            ✓
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    async markAsRead(notificationId) {
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
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
        }
    }

    escapeHtml(unsafe) {
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
});