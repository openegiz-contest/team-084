mergeInto(LibraryManager.library, {
  TynysSoftwareRenderer: function() { return window.tynysSoftwareRenderer ? 1 : 0; },
  TynysStatus: function(json) {
    var status = JSON.parse(UTF8ToString(json));
    window.tynysStatus = status;
    window.parent.postMessage({type: 'tynys-unity-data', status: status}, window.location.origin);
  }
});
