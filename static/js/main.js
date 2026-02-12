// UI/UX Enhancement Functions
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Handle form submissions in modals
    document.querySelectorAll('.modal-form').forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const submitBtn = form.querySelector('[type="submit"]');
            const originalText = submitBtn.innerHTML;
            
            // Show loading state
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

            fetch(form.action, {
                method: form.method,
                body: new FormData(form),
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                // Reset button state
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;

                if (data.success) {
                    // Hide modal
                    const modal = bootstrap.Modal.getInstance(form.closest('.modal'));
                    modal.hide();
                    
                    // Show success message
                    showToast(data.message || 'Operation completed successfully', 'success');
                    
                    // Refresh content if needed
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    } else if (data.reload) {
                        window.location.reload();
                    }
                } else {
                    showToast(data.message || 'An error occurred', 'error');
                }
            })
            .catch(error => {
                // Reset button state
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
                
                showToast('An unexpected error occurred', 'error');
                console.error('Error:', error);
            });
        });
    });

    // Add smooth scrolling to all anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });

    // Add animation classes to cards on scroll
    const animateOnScroll = () => {
        document.querySelectorAll('.card').forEach(card => {
            const cardTop = card.getBoundingClientRect().top;
            const triggerBottom = window.innerHeight * 0.8;

            if (cardTop < triggerBottom) {
                card.classList.add('fade-in');
            }
        });
    };

    window.addEventListener('scroll', animateOnScroll);
    animateOnScroll(); // Initial check

    // Handle delete confirmations
    document.querySelectorAll('[data-delete-url]').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const url = this.dataset.deleteUrl;
            const name = this.dataset.deleteName || 'item';
            const modalId = `delete-${Math.random().toString(36).substr(2, 9)}`;

            // Create and show modal
            const modal = document.createElement('div');
            modal.innerHTML = `
                <div class="modal fade" id="${modalId}">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                                    Confirm Delete
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <p>Are you sure you want to delete this ${name}?</p>
                                <p class="text-danger mb-0">
                                    <i class="fas fa-exclamation-triangle"></i>
                                    This action cannot be undone.
                                </p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    <i class="fas fa-times"></i> Cancel
                                </button>
                                <button type="button" class="btn btn-danger confirm-delete">
                                    <i class="fas fa-trash-alt"></i> Delete
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            const modalInstance = new bootstrap.Modal(document.getElementById(modalId));
            modalInstance.show();

            // Handle delete confirmation
            modal.querySelector('.confirm-delete').addEventListener('click', function() {
                this.disabled = true;
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';

                fetch(url, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    modalInstance.hide();
                    if (data.success) {
                        showToast(`${name} deleted successfully`, 'success');
                        const element = button.closest('[data-deletable]');
                        if (element) {
                            element.remove();
                        } else {
                            window.location.reload();
                        }
                    } else {
                        showToast(data.message || 'Failed to delete', 'error');
                    }
                })
                .catch(error => {
                    modalInstance.hide();
                    showToast('An unexpected error occurred', 'error');
                    console.error('Error:', error);
                })
                .finally(() => {
                    modal.remove();
                });
            });

            // Clean up modal when hidden
            modal.addEventListener('hidden.bs.modal', function() {
                modal.remove();
            });
        });
    });
});

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of toast (success, error, info, warning)
 */
function showToast(message, type = 'info') {
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#3b82f6',
        warning: '#f59e0b'
    };

    const icons = {
        success: '<i class="fas fa-check-circle me-2"></i>',
        error: '<i class="fas fa-exclamation-circle me-2"></i>',
        info: '<i class="fas fa-info-circle me-2"></i>',
        warning: '<i class="fas fa-exclamation-triangle me-2"></i>'
    };

    Toastify({
        text: icons[type] + message,
        duration: 3000,
        gravity: "top",
        position: "right",
        className: `toast-${type}`,
        style: {
            background: colors[type]
        }
    }).showToast();
}
