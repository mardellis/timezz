/* global TrelloPowerUp */

// Initialize the Trello Power-Up
TrelloPowerUp.initialize({
  'card-buttons': function(t, opts) {
    return [{
      icon: 'https://cdn.jsdelivr.net/npm/feather-icons/icons/play.svg',
      text: 'Start Timer',
      callback: function(t) {
        return t.popup({
          title: 'TimeZZ - Start Timer',
          url: './timer-popup.html',
          height: 200
        });
      }
    }];
  },
  
  'card-badges': function(t, opts) {
    return t.get('card', 'shared', 'timer')
    .then(function(timer) {
      if (timer && timer.active) {
        return [{
          icon: 'https://cdn.jsdelivr.net/npm/feather-icons/icons/clock.svg',
          text: 'Timer Active',
          color: 'green'
        }];
      }
      return [];
    });
  },

  'board-buttons': function(t, opts) {
    return [{
      icon: 'https://cdn.jsdelivr.net/npm/feather-icons/icons/bar-chart-2.svg',
      text: 'TimeZZ Dashboard',
      callback: function(t) {
        return t.popup({
          title: 'TimeZZ Dashboard',
          url: './dashboard-popup.html',
          height: 400
        });
      }
    }];
  }
});