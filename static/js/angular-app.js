var siaApp = angular.module('siaApp', ['ngMaterial']);

siaApp.config(['$interpolateProvider', function($interpolateProvider) {
  $interpolateProvider.startSymbol('{a');
  $interpolateProvider.endSymbol('a}');
}]);

siaApp.controller('SiaController', function SiaController($scope, $http, $interval) {
  $scope.queue = function(file_id){
    $http.get('/queue/' + file_id + "/604800").then(function(){window.location.href = "/downloads"}, function(){window.location.href = "/downloads"})
  }

  $scope.file_promises = {}

  $scope.update_file = function(file_id, identifier){
    $scope.file_promises[file_id] = $interval(function(file_id, identifier){
      $http.get('/file/' + file_id).then(function(res){
        document.getElementById(identifier).getElementsByClassName("bar-bbb")[0].style.width = res.data.uploadprogress + "%"
        if(res.data.uploadprogress == 100){
          $interval.cancel($scope.file_promises[file_id])
          document.getElementById(identifier).getElementsByClassName("progress-bars")[0].parentNode.removeChild(document.getElementById(identifier).getElementsByClassName("progress-bars")[0])
        if(res.data.available){
          document.getElementById(identifier).getElementsByTagName("a")[0].style.display = "inline"
          document.getElementById(identifier).getElementsByTagName("a")[0].onclick = function(){
            $scope.queue(res.data.file_id)
          }
        }
        }
      })
    }, 5000, 0, true, file_id, identifier)
  }

  $scope.toHuman = function(size) {
      var cutoff, i, j, len, selectedSize, selectedUnit, unit, units;
      selectedSize = 0;
      selectedUnit = "b";
      if (size > 0) {
        units = ['TB', 'GB', 'MB', 'KB', 'B'];
        for (i = j = 0, len = units.length; j < len; i = ++j) {
          unit = units[i];
          cutoff = Math.pow(1000, 4 - i);
          if (size >= cutoff) {
            selectedSize = size / Math.pow(1000, 4 - i);
            selectedUnit = unit;
            break;
          }
        }
        selectedSize = Math.round(10 * selectedSize) / 10;
      }
      return selectedSize + " " + selectedUnit;
    };
});

var r = new Resumable({
    target:'/upload',
    chunkSize: 2*1024*1024
});

r.assignBrowse(document.getElementById('add-button'));
r.assignDrop(document.getElementById('add-section'));

r.on('fileAdded', function(file){
  r.upload()
  div = document.createElement("div")
  div.id = file.uniqueIdentifier
  div.innerHTML = document.querySelector('#stuff-to-replicate').innerHTML
  div.getElementsByClassName("res-size")[0].innerHTML = angular.element(document.getElementById("ctrl-body")).scope().toHuman(file.size)
  div.getElementsByClassName("res-name")[0].innerHTML = file.fileName
  document.getElementById("file-preview").appendChild(div)
  });
r.on('fileProgress', function(file){
  document.getElementById(file.uniqueIdentifier).getElementsByClassName("bar-aaa")[0].style.width = file.progress()*100 + "%";
  });
r.on('fileSuccess', function(file, msg){
  angular.element(document.getElementById("ctrl-body")).scope().update_file(JSON.parse(msg).file_id, file.uniqueIdentifier)
  });
r.on('fileError', function(file, message){
  console.log(file)
  console.log("error!")
  console.log(message)
  document.getElementById(file.uniqueIdentifier).getElementsByClassName("bar-aaa")[0].style.backgroundColor = "red"
  });