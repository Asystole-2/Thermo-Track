document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('toggle-sidebar-btn');
    const collapseIcon = document.getElementById('collapse-icon');
    const logoText = document.getElementById('logo-text');

    const linkTexts = document.querySelectorAll('.link-text');
    const userGreeting = document.getElementById('user-greeting');
    const authLinksContainer = document.getElementById('auth-links');

    let isExpanded = true;
    const expandedWidth = '250px';
    const collapsedWidth = '80px';
    const transitionDuration = '300';

    const collapsibleElements = [logoText, userGreeting, ...Array.from(linkTexts)];
    if (authLinksContainer) {
        collapsibleElements.push(...Array.from(authLinksContainer.querySelectorAll('a')));
    }

    const initializeSidebar = () => {
        isExpanded = true;
        sidebar.style.width = expandedWidth;
        collapseIcon.style.transform = 'rotate(0deg)';

        collapsibleElements.forEach(el => {
            if (el) {
                el.style.opacity = 1;
                el.style.visibility = 'visible';
                el.style.transition = `opacity ${transitionDuration}ms ease-in-out, visibility 0ms`;
            }
        });
    };

    initializeSidebar();

    const toggleSidebar = () => {
        isExpanded = !isExpanded;

        if (isExpanded) {
            sidebar.style.width = expandedWidth;
            collapseIcon.style.transform = 'rotate(0deg)';

            setTimeout(() => {
                collapsibleElements.forEach(el => {
                    if (el) {
                        el.style.opacity = 1;
                        el.style.visibility = 'visible';
                    }
                });
            }, 50);

        } else {
            sidebar.style.width = collapsedWidth;
            collapseIcon.style.transform = 'rotate(180deg)';

            collapsibleElements.forEach(el => {
                if (el) {
                    el.style.opacity = 0;
                    setTimeout(() => {
                        el.style.visibility = 'hidden';
                    }, 200);
                }
            });
        }
    };

    toggleBtn.addEventListener('click', toggleSidebar);
});