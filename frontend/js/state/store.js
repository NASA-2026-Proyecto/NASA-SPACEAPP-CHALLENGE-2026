export function createStore(initialState) {
    let state = { ...initialState };
    const listeners = new Set();
  
    return {
      getState() {
        return state;
      },
  
      setState(patch) {
        const changes = typeof patch === 'function' ? patch(state) : patch;
        state = { ...state, ...changes };
        listeners.forEach((listener) => listener(state));
      },
  
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    };
  }