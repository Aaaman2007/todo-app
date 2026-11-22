// Ask before deleting anything.
document.querySelectorAll(".delete-form").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    if (!confirm('Delete "' + form.dataset.title + '"?')) event.preventDefault();
  });
});

// Keyboard shortcuts (skipped while typing in a field).
var titleInput = document.querySelector('.add input[name="title"]');

function isTyping(el) {
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "SELECT" ||
         el.tagName === "TEXTAREA" || el.isContentEditable;
}

document.addEventListener("keydown", function (event) {
  if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "/" || event.key === "n") {
    if (!titleInput) return;
    event.preventDefault();
    titleInput.focus();
  }
});
