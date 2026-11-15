export function bindDialog({ dialog, openButton }) {
    const open = () => dialog.showModal();
  
    // Cerrar al pulsar fuera del contenido
    const onDialogClick = (event) => {
      if (event.target === dialog) dialog.close();
    };
  
    openButton.addEventListener('click', open);
    dialog.addEventListener('click', onDialogClick);
  
    return function unbind() {
      openButton.removeEventListener('click', open);
      dialog.removeEventListener('click', onDialogClick);
    };
  }