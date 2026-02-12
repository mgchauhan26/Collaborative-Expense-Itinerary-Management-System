// Itinerary form validation and enhancement
document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form');
    const dateInput = document.querySelector('[name="date"]');
    const timeInput = document.querySelector('[name="time"]');
    
    if (!form || !dateInput || !timeInput) return;

    // Get trip dates from data attributes
    const tripStartDate = form.dataset.tripStartDate;
    const tripEndDate = form.dataset.tripEndDate;
    
    // Set min and max dates on the input
    dateInput.min = tripStartDate;
    dateInput.max = tripEndDate;

    // Set default time if not set
    if (!timeInput.value) {
        const now = new Date();
        timeInput.value = now.getHours().toString().padStart(2, '0') + ':' + 
                        now.getMinutes().toString().padStart(2, '0');
    }

    // Date validation function
    function validateDate(date) {
        return date >= tripStartDate && date <= tripEndDate;
    }

    // Show validation feedback
    function showFeedback(element, isValid, message) {
        const errorId = `${element.name}-error`;
        let errorElement = document.getElementById(errorId);
        
        if (!isValid) {
            if (!errorElement) {
                errorElement = document.createElement('div');
                errorElement.id = errorId;
                errorElement.className = 'invalid-feedback';
                element.parentNode.appendChild(errorElement);
            }
            errorElement.textContent = message;
            element.classList.add('is-invalid');
            element.classList.remove('is-valid');
        } else {
            if (errorElement) {
                errorElement.remove();
            }
            element.classList.remove('is-invalid');
            element.classList.add('is-valid');
        }
        return isValid;
    }

    // Date input validation
    dateInput.addEventListener('input', function() {
        const isValid = validateDate(this.value);
        showFeedback(this, isValid, '❌ The itinerary date must be between the trip\'s start and end dates.');
    });

    // Time input validation
    timeInput.addEventListener('input', function() {
        const isValid = this.value.trim() !== '';
        showFeedback(this, isValid, '❌ Please enter a valid time.');
    });

    // Form submission validation
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Validate both date and time
        const dateValid = validateDate(dateInput.value);
        const timeValid = timeInput.value.trim() !== '';
        
        showFeedback(dateInput, dateValid, '❌ The itinerary date must be between the trip\'s start and end dates.');
        showFeedback(timeInput, timeValid, '❌ Please enter a valid time.');
        
        if (dateValid && timeValid) {
            this.submit();
        } else {
            if (!dateValid) {
                dateInput.focus();
            } else {
                timeInput.focus();
            }
            
            // Show toast notification
            Toastify({
                text: "Please fix the form errors before submitting.",
                duration: 3000,
                close: true,
                gravity: "top",
                position: "right",
                style: {
                    background: "#dc3545"
                }
            }).showToast();
        }
    });
}); {
            const selectedDate = dateInput.value;
            
            if (selectedDate < tripStartDate || selectedDate > tripEndDate) {
                e.preventDefault();
                // Show toast notification
                Toastify({
                    text: "❌ The itinerary date must be between the trip's start and end dates.",
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    className: "toast-error",
                    style: {
                        background: "#dc3545"
                    }
                }).showToast();
                
                dateInput.focus();
            }
        });
    }
});