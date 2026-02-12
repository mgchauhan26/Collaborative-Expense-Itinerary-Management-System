// Trip form handling
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('createTripForm');
    if (!form) return;

    const start = form.querySelector('[name="start_date"]');
    const end = form.querySelector('[name="end_date"]');
    const title = form.querySelector('[name="title"]');
    const dest = form.querySelector('[name="destination"]');
    const coverImage = document.getElementById('cover_image');
    const imagePreview = document.getElementById('imagePreview');
    const removeImageBtn = document.getElementById('removeImage');
    const today = new Date();
    today.setHours(0,0,0,0);

    // Function to show error feedback
    function showError(message, element) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback d-block';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-circle me-1"></i>${message}`;
        
        // Remove any existing error messages
        const existingError = element.parentNode.querySelector('.invalid-feedback');
        if (existingError) {
            existingError.remove();
        }
        
        element.classList.add('is-invalid');
        element.parentNode.appendChild(errorDiv);
    }

    // Function to show success feedback
    function showSuccess(element) {
        element.classList.remove('is-invalid');
        element.classList.add('is-valid');
        const error = element.parentNode.querySelector('.invalid-feedback');
        if (error) {
            error.remove();
        }
    }

    // Handle file selection
    if (coverImage) {
        coverImage.addEventListener('change', function(e) {
            const file = this.files[0];
            
            // Reset preview and validation
            imagePreview.classList.add('d-none');
            this.classList.remove('is-valid', 'is-invalid');
            
            if (file) {
                // Validate file type
                const fileType = file.type.toLowerCase();
                if (!['image/jpeg', 'image/jpg', 'image/png'].includes(fileType)) {
                    showError('Please select a valid image file (JPG or PNG)', this);
                    this.value = '';
                    return;
                }
                
                // Validate file size (16MB)
                if (file.size > 16 * 1024 * 1024) {
                    showError('Image file must be smaller than 16MB', this);
                    this.value = '';
                    return;
                }
                
                // Show preview
                const reader = new FileReader();
                reader.onload = function(e) {
                    const img = imagePreview.querySelector('img');
                    img.src = e.target.result;
                    imagePreview.classList.remove('d-none');
                    showSuccess(coverImage);
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Handle remove image button
    if (removeImageBtn) {
        removeImageBtn.addEventListener('click', function() {
            coverImage.value = '';
            imagePreview.classList.add('d-none');
            coverImage.classList.remove('is-valid', 'is-invalid');
            const error = coverImage.parentNode.querySelector('.invalid-feedback');
            if (error) {
                error.remove();
            }
        });
    }

    // Form validation
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        e.stopPropagation(); // Prevent other handlers from processing this event
        let isValid = true;
        
        // Clear all previous errors
        form.querySelectorAll('.invalid-feedback').forEach(el => el.remove());
        form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
        form.querySelectorAll('.is-valid').forEach(el => el.classList.remove('is-valid'));
        
        // Title validation
        if (!title.value || title.value.trim().length < 3) {
            showError('Trip title must be at least 3 characters', title);
            isValid = false;
        } else {
            showSuccess(title);
        }

        // Destination validation
        const destRe = /^[A-Za-z ]+$/;
        if (!dest.value || !destRe.test(dest.value.trim())) {
            showError('Destination must contain only letters and spaces', dest);
            isValid = false;
        } else {
            showSuccess(dest);
        }

        // Date validation
        if (start.value && end.value) {
            const startDate = new Date(start.value);
            const endDate = new Date(end.value);
            startDate.setHours(0,0,0,0);
            endDate.setHours(0,0,0,0);

            if (startDate < today) {
                showError('Start date cannot be in the past', start);
                isValid = false;
            } else {
                showSuccess(start);
            }

            if (endDate < startDate) {
                showError('End date must be after start date', end);
                isValid = false;
            } else {
                showSuccess(end);
            }
        } else {
            if (!start.value) {
                showError('Start date is required', start);
                isValid = false;
            }
            if (!end.value) {
                showError('End date is required', end);
                isValid = false;
            }
        }

        if (!isValid) {
            // Show error message
            const errorMessage = "Please correct the errors before submitting";
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-danger';
            alertDiv.innerHTML = `<i class="fas fa-exclamation-circle me-2"></i>${errorMessage}`;
            form.insertBefore(alertDiv, form.firstChild);
            alertDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
            return;
        }

        // Prevent double submission
        if (form.dataset.submitting === 'true') {
            return;
        }
        form.dataset.submitting = 'true';

        // Submit form
        const formData = new FormData(form);
        const submitButton = form.querySelector('button[type="submit"]');
        const originalText = submitButton.innerHTML;
        
        submitButton.disabled = true;
        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Creating Trip...';

        const formAction = form.action || window.location.pathname;
        fetch(formAction, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
                return;
            }
            return response.text().then(html => {
                // Check if response is JSON
                try {
                    const data = JSON.parse(html);
                    if (data.success) {
                        window.location.href = data.redirect || '/dashboard';
                        return;
                    }
                    throw new Error(data.message || 'An error occurred');
                } catch {
                    // Not JSON, replace page content with new HTML
                    document.documentElement.innerHTML = html;
                }
            });
        })
        .catch(error => {
            console.error('Error:', error);
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-danger';
            alertDiv.innerHTML = `<i class="fas fa-exclamation-circle me-2"></i>An unexpected error occurred. Please try again.`;
            form.insertBefore(alertDiv, form.firstChild);
            alertDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
        })
        .finally(() => {
            submitButton.disabled = false;
            submitButton.innerHTML = originalText;
            form.dataset.submitting = 'false';
        });
    });
});