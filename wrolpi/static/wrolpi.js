function scroll_to_top() {
    $("html, body").animate({scrollTop: 0}, "slow");
}

function get_spinner(elem) {
    return $('#' + elem.id).find('.spinner-border');
}

function show_spinner(elem) {
    let spinner = get_spinner(elem);
    spinner.show();
}

function hide_spinner(elem) {
    let spinner = get_spinner(elem);
    spinner.hide();
}

function get_button_xmark(elem) {
    return $('#' + elem.id).find('.xmark');
}

function show_xmark(elem) {
    let checkmark = get_button_xmark(elem);
    checkmark.show();
}

function hide_xmark(elem) {
    let checkmark = get_button_xmark(elem);
    checkmark.hide();
}

function get_button_checkmark(elem) {
    return $('#' + elem.id).find('.checkmark');
}

function show_checkmark(elem) {
    let checkmark = get_button_checkmark(elem);
    checkmark.show();
}

function hide_checkmark(elem) {
    let checkmark = get_button_checkmark(elem);
    checkmark.hide();
}

function attach_feed(elem, stream_url) {
    console.log('attach-feed');
    let form = $(elem).parents('form:first');
    let stream_pre = form.find('pre.stream-feed');
    let socket = new WebSocket(stream_url, 'protocolOne');
    console.log(socket);
    socket.onmessage = function(event) {
        console.log(event.data);
        stream_pre.text = event.data;
    }
}


form_response_handler = function (button, response) {
    console.log(response);
    hide_spinner(button);
    console.log('stream-url', response['stream-url']);
    if (response.hasOwnProperty('stream-url') && response["stream-url"]) {
        attach_feed(button, response["stream-url"])
    }
    if (response.hasOwnProperty('success')) {
        console.log('success');
        hide_xmark(button);
        show_checkmark(button);
    } else {
        console.log('failure');
        show_xmark(button);
        hide_checkmark(button);
    }
};

submit_form = function (method, button) {
    event.preventDefault();
    console.log('submit_form: ' + method);

    show_spinner(button);

    console.log(button.form);
    let url = button.form.action;
    let form = $('form#' + button.form.id);

    console.log('url');
    $.ajax({
        url: url,
        type: method.toUpperCase(),
        dataType: 'json',
        data: form.serialize(),
        success: function (response) {
            form_response_handler(button, response);
        },
        error: function (response) {
            form_response_handler(button, response);
        },
    });
};

put_form = function (button) {
    return submit_form('PUT', button)
};
get_form = function (button) {
    return submit_form('GET', button)
};
post_form = function (button) {
    return submit_form('POST', button)
};
delete_form = function (button) {
    return submit_form('DELETE', button)
};
