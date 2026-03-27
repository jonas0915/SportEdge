function picksList() {
    return {
        startRefresh(seconds) {
            if (seconds > 0) {
                setInterval(() => window.location.reload(), seconds * 1000);
            }
        }
    }
}

function copyBet(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Brief visual feedback could be added here
    });
}
